"""CanMV K230 Phase 0 capability probe.

This module deliberately uses a small MicroPython-compatible subset. Hardware
steps are feature-detected and isolated so one firmware API difference cannot
erase the rest of the report.
"""

try:
    import ujson as json
except ImportError:
    import json

import gc
import os
import sys
import time


DEFAULT_DEVICE_CONFIG = "config/device.json"
DEFAULT_PROBE_CONFIG = "config/probe.json"


def _ticks_ms():
    function = getattr(time, "ticks_ms", None)
    if function is not None:
        return function()
    return int(time.time() * 1000)


def _ticks_diff(current, previous):
    function = getattr(time, "ticks_diff", None)
    if function is not None:
        return function(current, previous)
    return current - previous


def _sleep_ms(milliseconds):
    function = getattr(time, "sleep_ms", None)
    if function is not None:
        function(int(milliseconds))
    else:
        time.sleep(float(milliseconds) / 1000.0)


def _exitpoint():
    function = getattr(os, "exitpoint", None)
    if function is not None:
        try:
            function()
        except BaseException:
            pass


def _json_load(path, default):
    try:
        with open(path, "r") as handle:
            value = json.loads(handle.read())
        return value if isinstance(value, dict) else default
    except BaseException:
        return default


def _merge(base, override):
    result = dict(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _safe_value(value, depth=0):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth >= 5:
        return repr(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except BaseException:
            return repr(value)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[str(key)] = _safe_value(item, depth + 1)
        return result
    return repr(value)


def _ensure_directory(path):
    if not path:
        return
    normalized = path.replace("\\", "/")
    absolute = normalized.startswith("/")
    current = "/" if absolute else ""
    for part in normalized.split("/"):
        if not part:
            continue
        if current in ("", "/"):
            current = current + part
        else:
            current = current + "/" + part
        try:
            os.stat(current)
        except BaseException:
            try:
                os.mkdir(current)
            except BaseException:
                pass


def _ensure_parent(path):
    normalized = path.replace("\\", "/")
    if "/" in normalized:
        _ensure_directory(normalized.rsplit("/", 1)[0])


def _write_json(path, value):
    _ensure_parent(path)
    temporary = path + ".tmp"
    with open(temporary, "w") as handle:
        handle.write(json.dumps(_safe_value(value)))
        handle.write("\n")
    try:
        os.remove(path)
    except BaseException:
        pass
    os.rename(temporary, path)


def _append_json_line(path, value):
    _ensure_parent(path)
    with open(path, "a") as handle:
        handle.write(json.dumps(_safe_value(value)))
        handle.write("\n")


def _memory_snapshot():
    gc.collect()
    result = {}
    for name in ("mem_free", "mem_alloc"):
        function = getattr(gc, name, None)
        if function is not None:
            try:
                result[name] = int(function())
            except BaseException as error:
                result[name + "_error"] = repr(error)
    try:
        import machine

        temperature = getattr(machine, "temperature", None)
        if temperature is not None:
            result["temperature_c"] = float(temperature())
    except BaseException:
        pass
    return result


def _print_exception(error):
    function = getattr(sys, "print_exception", None)
    if function is not None:
        try:
            function(error)
            return
        except BaseException:
            pass
    print("probe exception:", repr(error))


class ProbeReport:
    def __init__(self, path, expected_device):
        self.path = path
        self.report = {
            "schema_version": 1,
            "probe": "nuedc_k230_phase0",
            "status": "running",
            "started_ms": _ticks_ms(),
            "expected_device": _safe_value(expected_device),
            "steps": [],
            "error_count": 0,
        }
        self.save()

    def save(self):
        _write_json(self.path, self.report)

    def skip(self, name, reason):
        self.report["steps"].append(
            {
                "name": name,
                "status": "skipped",
                "reason": reason,
                "memory": _memory_snapshot(),
            }
        )
        self.save()

    def run(self, name, function):
        print("[phase0] start", name)
        started = _ticks_ms()
        entry = {
            "name": name,
            "status": "running",
            "memory_before": _memory_snapshot(),
        }
        self.report["steps"].append(entry)
        self.save()
        try:
            entry["data"] = _safe_value(function())
            entry["status"] = "ok"
        except BaseException as error:
            entry["status"] = "error"
            entry["error_type"] = type(error).__name__
            entry["error"] = repr(error)
            self.report["error_count"] += 1
            _print_exception(error)
        entry["elapsed_ms"] = int(_ticks_diff(_ticks_ms(), started))
        entry["memory_after"] = _memory_snapshot()
        self.save()
        print("[phase0]", entry["status"], name, entry["elapsed_ms"], "ms")
        return entry

    def finish(self):
        self.report["finished_ms"] = _ticks_ms()
        self.report["elapsed_ms"] = int(
            _ticks_diff(self.report["finished_ms"], self.report["started_ms"])
        )
        if self.report["error_count"]:
            self.report["status"] = "complete_with_errors"
        else:
            self.report["status"] = "complete"
        self.report["final_memory"] = _memory_snapshot()
        self.save()
        return self.report


def _import_module(name):
    return __import__(name, None, None, ("*",))


def _public_names(module):
    return sorted(name for name in dir(module) if not name.startswith("_"))


def _feature_map(module, names):
    return {name: hasattr(module, name) for name in names}


def _probe_runtime():
    result = {
        "sys_version": getattr(sys, "version", None),
        "sys_platform": getattr(sys, "platform", None),
        "implementation": _safe_value(getattr(sys, "implementation", None)),
        "path": _safe_value(getattr(sys, "path", None)),
        "memory": _memory_snapshot(),
    }
    try:
        result["cwd"] = os.getcwd()
    except BaseException as error:
        result["cwd_error"] = repr(error)
    try:
        result["uname"] = _safe_value(os.uname())
    except BaseException as error:
        result["uname_error"] = repr(error)
    for path in ("/sdcard", "/data", "."):
        try:
            result["statvfs_" + path.replace("/", "_")] = _safe_value(
                os.statvfs(path)
            )
        except BaseException:
            pass
    return result


MODULE_FEATURES = {
    "media.sensor": [
        "Sensor",
        "CAM_CHN_ID_0",
        "CAM_CHN_ID_1",
        "CAM_CHN_ID_2",
        "RGB888",
        "RGBP888",
        "YUV420SP",
        "GRAYSCALE",
    ],
    "media.display": ["Display", "ALIGN_UP"],
    "media.media": ["MediaManager"],
    "image": [
        "Image",
        "RGB565",
        "RGB888",
        "ARGB8888",
        "GRAYSCALE",
        "EDGE_CANNY",
    ],
    "cv_lite": [],
    "ulab.numpy": ["ndarray", "array", "zeros", "mean"],
    "lvgl": [],
    "machine": ["TOUCH", "temperature", "chipid"],
    "nncase_runtime": ["kpu", "ai2d", "from_numpy"],
    "nonai2d": ["CSC"],
}


def _probe_modules():
    result = {}
    keywords = (
        "undistort",
        "pnp",
        "warp",
        "perspective",
        "corner",
        "contour",
        "line",
        "rect",
        "circle",
        "blob",
    )
    for name, features in MODULE_FEATURES.items():
        item = {}
        try:
            module = _import_module(name)
            item["available"] = True
            item["features"] = _feature_map(module, features)
            if name in ("cv_lite", "lvgl"):
                names = _public_names(module)
                item["matching_api"] = [
                    value for value in names if any(key in value.lower() for key in keywords)
                ]
                item["public_name_count"] = len(names)
        except BaseException as error:
            item["available"] = False
            item["error"] = repr(error)
        result[name] = item
    return result


def _sensor_constant(sensor_module, sensor_class, name):
    if hasattr(sensor_module, name):
        return getattr(sensor_module, name)
    if hasattr(sensor_class, name):
        return getattr(sensor_class, name)
    raise AttributeError("missing Sensor constant " + name)


def _sensor_modes(sensor_module, expected_name):
    sensor_class = sensor_module.Sensor
    list_mode = getattr(sensor_class, "list_mode", None)
    result = {"ports": [], "selected_csi": None}
    if list_mode is None:
        result["list_mode_available"] = False
        return result
    result["list_mode_available"] = True
    for csi_id in (0, 1, 2):
        item = {"csi_id": csi_id}
        try:
            sensor_name, modes = list_mode(id=csi_id)
            item["sensor_name"] = str(sensor_name)
            item["modes"] = _safe_value(modes)
            if (
                result["selected_csi"] is None
                and expected_name.lower() in str(sensor_name).lower()
            ):
                result["selected_csi"] = csi_id
        except BaseException as error:
            item["error"] = repr(error)
        result["ports"].append(item)
    return result


def _selected_csi(sensor_module, device):
    configured = device.get("camera", {}).get("csi_id")
    if configured is not None:
        return int(configured)
    expected = str(device.get("camera", {}).get("sensor", "GC2093"))
    modes = _sensor_modes(sensor_module, expected)
    return modes.get("selected_csi")


def _new_sensor(sensor_module, device):
    camera = device.get("camera", {})
    parameters = {
        "width": int(camera.get("capture_width", 1920)),
        "height": int(camera.get("capture_height", 1080)),
        "fps": 30,
    }
    csi_id = _selected_csi(sensor_module, device)
    if csi_id is not None:
        parameters["id"] = csi_id
    return sensor_module.Sensor(**parameters), csi_id


def _image_info(image_object):
    result = {"type": type(image_object).__name__}
    for name in ("width", "height", "format", "size", "poolid"):
        value = getattr(image_object, name, None)
        if value is None:
            continue
        try:
            result[name] = _safe_value(value() if callable(value) else value)
        except BaseException as error:
            result[name + "_error"] = repr(error)
    return result


def _array_info(array):
    result = {"type": type(array).__name__}
    for name in ("shape", "dtype", "size", "ndim"):
        try:
            result[name] = _safe_value(getattr(array, name))
        except BaseException:
            pass
    return result


def _cleanup_media(sensor=None, display=None, media_manager=None, touch=None):
    errors = []
    if sensor is not None:
        try:
            sensor.stop()
        except BaseException as error:
            errors.append("sensor.stop: " + repr(error))
    if touch is not None:
        deinit = getattr(touch, "deinit", None)
        if deinit is not None:
            try:
                deinit()
            except BaseException as error:
                errors.append("touch.deinit: " + repr(error))
    if display is not None:
        try:
            display.deinit()
        except BaseException as error:
            errors.append("Display.deinit: " + repr(error))
    _sleep_ms(100)
    if media_manager is not None:
        try:
            media_manager.deinit()
        except BaseException as error:
            errors.append("MediaManager.deinit: " + repr(error))
    gc.collect()
    return errors


def _probe_sensor_modes(device):
    sensor_module = _import_module("media.sensor")
    expected = str(device.get("camera", {}).get("sensor", "GC2093"))
    return _sensor_modes(sensor_module, expected)


def _save_image(image_object, path):
    _ensure_parent(path)
    try:
        image_object.save(path, quality=95)
    except TypeError:
        image_object.save(path)
    return path


def _probe_camera(device, config):
    sensor_module = _import_module("media.sensor")
    media_module = _import_module("media.media")
    sensor_class = sensor_module.Sensor
    sensor = None
    media_manager = media_module.MediaManager
    result = {}
    try:
        sensor, csi_id = _new_sensor(sensor_module, device)
        result["selected_csi"] = csi_id
        sensor.reset()
        channel = _sensor_constant(sensor_module, sensor_class, "CAM_CHN_ID_0")
        rgb888 = _sensor_constant(sensor_module, sensor_class, "RGB888")
        camera = device.get("camera", {})
        width = int(camera.get("capture_width", 1920))
        height = int(camera.get("capture_height", 1080))
        sensor.set_framesize(width=width, height=height, chn=channel)
        sensor.set_pixformat(rgb888, chn=channel)
        media_manager.init()
        sensor.run()
        result["sensor_type"] = _safe_value(sensor.get_type()) if hasattr(sensor, "get_type") else None
        result["actual_width"] = int(sensor.width(chn=channel))
        result["actual_height"] = int(sensor.height(chn=channel))
        for _ in range(int(config.get("camera_warmup_frames", 3))):
            warmup = sensor.snapshot(chn=channel)
            del warmup
        samples = []
        last_image = None
        count = max(1, int(config.get("capture_samples", 3)))
        for _ in range(count):
            started = _ticks_ms()
            last_image = sensor.snapshot(chn=channel)
            elapsed = int(_ticks_diff(_ticks_ms(), started))
            samples.append({"snapshot_ms": elapsed, "image": _image_info(last_image)})
            if len(samples) < count:
                del last_image
                last_image = None
        result["samples"] = samples
        if last_image is not None and hasattr(last_image, "to_numpy_ref"):
            started = _ticks_ms()
            array = last_image.to_numpy_ref()
            result["numpy_ref_ms"] = int(_ticks_diff(_ticks_ms(), started))
            result["numpy_ref"] = _array_info(array)
            del array
        if last_image is not None and config.get("save_sample_image", True):
            result["sample_image"] = _save_image(
                last_image, config.get("sample_image_path")
            )
        if last_image is not None:
            del last_image
        for name in ("get_again_range", "get_exposure_time_range", "get_hmirror", "get_vflip"):
            function = getattr(sensor, name, None)
            if function is not None:
                try:
                    result[name] = _safe_value(function())
                except BaseException as error:
                    result[name + "_error"] = repr(error)
        return result
    finally:
        cleanup = _cleanup_media(sensor=sensor, media_manager=media_manager)
        if cleanup:
            print("camera cleanup warnings:", cleanup)


def _probe_display_touch(device, config):
    display_module = _import_module("media.display")
    media_module = _import_module("media.media")
    image_module = _import_module("image")
    machine_module = _import_module("machine")
    display = display_module.Display
    media_manager = media_module.MediaManager
    touch = None
    canvas = None
    result = {"touch_points": []}
    try:
        display_config = device.get("display", {})
        width = int(display_config.get("width", 800))
        height = int(display_config.get("height", 480))
        display_type = getattr(display, str(display_config.get("driver", "ST7701")))
        display.init(
            display_type,
            width=width,
            height=height,
            to_ide=bool(config.get("display_to_ide", True)),
        )
        media_manager.init()
        pixel_format = getattr(image_module, "ARGB8888", None)
        if pixel_format is None:
            pixel_format = getattr(image_module, "RGB565")
        canvas = image_module.Image(width, height, pixel_format)
        canvas.clear()
        message = "NEUDC K230 Phase 0 - touch screen now"
        draw_advanced = getattr(canvas, "draw_string_advanced", None)
        if draw_advanced is not None:
            draw_advanced(20, 30, 28, message, color=(255, 255, 255))
        else:
            canvas.draw_string(20, 30, message, color=(255, 255, 255))
        display.show_image(canvas)
        touch_class = getattr(machine_module, "TOUCH")
        touch = touch_class(int(display_config.get("touch_index", 0)))
        wait_ms = max(0, int(config.get("touch_wait_ms", 5000)))
        started = _ticks_ms()
        while _ticks_diff(_ticks_ms(), started) < wait_ms:
            points = touch.read(5)
            if points:
                for point in points:
                    result["touch_points"].append(
                        {
                            "x": int(point.x),
                            "y": int(point.y),
                            "event": _safe_value(getattr(point, "event", None)),
                            "track_id": _safe_value(getattr(point, "track_id", None)),
                        }
                    )
                if len(result["touch_points"]) >= 3:
                    break
            _exitpoint()
            _sleep_ms(50)
        result["display"] = {"width": width, "height": height, "type": str(display_type)}
        result["touch_observed"] = bool(result["touch_points"])
        return result
    finally:
        if canvas is not None:
            del canvas
        cleanup = _cleanup_media(
            display=display, media_manager=media_manager, touch=touch
        )
        if cleanup:
            print("display cleanup warnings:", cleanup)


def _set_framesize_with_optional_crop(sensor, width, height, channel):
    try:
        sensor.set_framesize(
            width=width, height=height, chn=channel, crop=True
        )
        return True
    except TypeError:
        sensor.set_framesize(width=width, height=height, chn=channel)
        return False


def _probe_combined_pipeline(device, config):
    sensor_module = _import_module("media.sensor")
    display_module = _import_module("media.display")
    media_module = _import_module("media.media")
    sensor_class = sensor_module.Sensor
    display = display_module.Display
    media_manager = media_module.MediaManager
    sensor = None
    result = {}
    try:
        sensor, csi_id = _new_sensor(sensor_module, device)
        result["selected_csi"] = csi_id
        sensor.reset()
        display_channel = _sensor_constant(
            sensor_module, sensor_class, "CAM_CHN_ID_0"
        )
        algorithm_channel = _sensor_constant(
            sensor_module, sensor_class, "CAM_CHN_ID_1"
        )
        rgb888 = _sensor_constant(sensor_module, sensor_class, "RGB888")
        yuv420 = _sensor_constant(sensor_module, sensor_class, "YUV420SP")
        camera = device.get("camera", {})
        display_config = device.get("display", {})
        capture_width = int(camera.get("capture_width", 1920))
        capture_height = int(camera.get("capture_height", 1080))
        display_width = int(display_config.get("width", 800))
        display_height = int(display_config.get("height", 480))
        result["display_crop_requested"] = _set_framesize_with_optional_crop(
            sensor, display_width, display_height, display_channel
        )
        sensor.set_pixformat(yuv420, chn=display_channel)
        sensor.set_framesize(
            width=capture_width,
            height=capture_height,
            chn=algorithm_channel,
        )
        sensor.set_pixformat(rgb888, chn=algorithm_channel)
        bind_info = sensor.bind_info(x=0, y=0, chn=display_channel)
        display.bind_layer(**bind_info, layer=display.LAYER_VIDEO1)
        display_type = getattr(display, str(display_config.get("driver", "ST7701")))
        display.init(
            display_type,
            width=display_width,
            height=display_height,
            to_ide=bool(config.get("display_to_ide", True)),
        )
        media_manager.init()
        sensor.run()
        for _ in range(int(config.get("camera_warmup_frames", 3))):
            warmup = sensor.snapshot(chn=algorithm_channel)
            del warmup
        samples = []
        for _ in range(max(1, int(config.get("capture_samples", 3)))):
            started = _ticks_ms()
            frame = sensor.snapshot(chn=algorithm_channel)
            samples.append(
                {
                    "snapshot_ms": int(_ticks_diff(_ticks_ms(), started)),
                    "image": _image_info(frame),
                }
            )
            del frame
        result["samples"] = samples
        result["algorithm_channel"] = {
            "id": algorithm_channel,
            "width": int(sensor.width(chn=algorithm_channel)),
            "height": int(sensor.height(chn=algorithm_channel)),
            "format": "RGB888",
        }
        result["display_channel"] = {
            "id": display_channel,
            "width": int(sensor.width(chn=display_channel)),
            "height": int(sensor.height(chn=display_channel)),
            "format": "YUV420SP",
            "bind_info": _safe_value(bind_info),
        }
        return result
    finally:
        cleanup = _cleanup_media(
            sensor=sensor, display=display, media_manager=media_manager
        )
        if cleanup:
            print("combined cleanup warnings:", cleanup)


def _result_summary(value):
    if value is None:
        return None
    try:
        return {"type": type(value).__name__, "length": len(value)}
    except BaseException:
        return {"type": type(value).__name__, "value": _safe_value(value)}


def _benchmark(name, function):
    started = _ticks_ms()
    value = function()
    elapsed = int(_ticks_diff(_ticks_ms(), started))
    summary = _result_summary(value)
    del value
    gc.collect()
    return {"name": name, "elapsed_ms": elapsed, "result": summary}


def _probe_image_primitives():
    image_module = _import_module("image")
    grayscale = getattr(image_module, "GRAYSCALE")
    base = image_module.Image(640, 480, grayscale)
    base.clear()
    base.draw_rectangle((80, 60, 480, 360), color=255, thickness=5)
    base.draw_line((80, 60, 560, 420), color=255, thickness=3)
    base.draw_line((560, 60, 80, 420), color=255, thickness=3)
    benchmarks = []

    def on_copy(method, *args, **kwargs):
        image_copy = base.copy()
        try:
            return getattr(image_copy, method)(*args, **kwargs)
        finally:
            del image_copy

    operations = [
        ("binary", lambda: on_copy("binary", [(0, 127)])),
        ("erode", lambda: on_copy("erode", 1)),
        ("dilate", lambda: on_copy("dilate", 1)),
        ("find_lines", lambda: base.find_lines(threshold=1000)),
        ("find_line_segments", lambda: base.find_line_segments()),
        ("find_rects", lambda: base.find_rects(threshold=1000)),
    ]
    edge_constant = getattr(image_module, "EDGE_CANNY", None)
    if edge_constant is not None:
        operations.append(
            (
                "find_edges_canny",
                lambda: on_copy(
                    "find_edges", edge_constant, threshold=(50, 80)
                ),
            )
        )
    for name, function in operations:
        try:
            benchmarks.append(_benchmark(name, function))
        except BaseException as error:
            benchmarks.append({"name": name, "error": repr(error)})
    del base
    cv_lite = None
    try:
        cv_lite = _import_module("cv_lite")
    except BaseException:
        pass
    matching = []
    if cv_lite is not None:
        for name in _public_names(cv_lite):
            lowered = name.lower()
            if any(
                keyword in lowered
                for keyword in ("undistort", "pnp", "warp", "perspective")
            ):
                matching.append(name)
    return {"synthetic_image": [640, 480], "benchmarks": benchmarks, "cv_lite_geometry_api": matching}


def _probe_stability(device, config):
    duration = max(0, int(config.get("stability_seconds", 0)))
    if duration <= 0:
        return {"duration_seconds": 0, "message": "disabled"}
    sensor_module = _import_module("media.sensor")
    media_module = _import_module("media.media")
    sensor_class = sensor_module.Sensor
    media_manager = media_module.MediaManager
    sensor = None
    samples = []
    frame_count = 0
    log_path = config.get("stability_log_path")
    try:
        try:
            os.remove(log_path)
        except BaseException:
            pass
        sensor, csi_id = _new_sensor(sensor_module, device)
        sensor.reset()
        channel = _sensor_constant(sensor_module, sensor_class, "CAM_CHN_ID_0")
        rgb888 = _sensor_constant(sensor_module, sensor_class, "RGB888")
        camera = device.get("camera", {})
        sensor.set_framesize(
            width=int(camera.get("capture_width", 1920)),
            height=int(camera.get("capture_height", 1080)),
            chn=channel,
        )
        sensor.set_pixformat(rgb888, chn=channel)
        media_manager.init()
        sensor.run()
        started = _ticks_ms()
        next_sample = started
        interval_ms = max(
            1000,
            int(config.get("stability_sample_interval_seconds", 10)) * 1000,
        )
        while _ticks_diff(_ticks_ms(), started) < duration * 1000:
            frame_started = _ticks_ms()
            frame = sensor.snapshot(chn=channel)
            frame_ms = int(_ticks_diff(_ticks_ms(), frame_started))
            del frame
            frame_count += 1
            current = _ticks_ms()
            if _ticks_diff(current, next_sample) >= 0:
                sample = {
                    "elapsed_ms": int(_ticks_diff(current, started)),
                    "frame_count": frame_count,
                    "last_frame_ms": frame_ms,
                    "memory": _memory_snapshot(),
                }
                samples.append(sample)
                _append_json_line(log_path, sample)
                print("STABILITY_SAMPLE", json.dumps(sample))
                next_sample = current + interval_ms
            _exitpoint()
        return {
            "selected_csi": csi_id,
            "duration_seconds": duration,
            "frame_count": frame_count,
            "samples": samples,
            "log_path": log_path,
        }
    finally:
        cleanup = _cleanup_media(sensor=sensor, media_manager=media_manager)
        if cleanup:
            print("stability cleanup warnings:", cleanup)


def run_phase0_probe(
    device_path=DEFAULT_DEVICE_CONFIG,
    config_path=DEFAULT_PROBE_CONFIG,
    config_override=None,
    output_path=None,
):
    device = _json_load(device_path, {})
    config = _json_load(config_path, {})
    if config_override:
        config = _merge(config, config_override)
    report_path = output_path or config.get(
        "report_path", "runtime/phase0/runtime_probe.json"
    )
    reporter = ProbeReport(report_path, device)
    reporter.run("runtime", _probe_runtime)
    reporter.run("module_inventory", _probe_modules)
    reporter.run("sensor_modes", lambda: _probe_sensor_modes(device))

    if config.get("run_camera", True):
        reporter.run("camera_1920x1080_rgb888", lambda: _probe_camera(device, config))
    else:
        reporter.skip("camera_1920x1080_rgb888", "disabled by config")

    if config.get("run_display_touch", True):
        reporter.run("display_800x480_touch", lambda: _probe_display_touch(device, config))
    else:
        reporter.skip("display_800x480_touch", "disabled by config")

    if config.get("run_combined_pipeline", True):
        reporter.run(
            "combined_display_ch0_algorithm_ch1",
            lambda: _probe_combined_pipeline(device, config),
        )
    else:
        reporter.skip(
            "combined_display_ch0_algorithm_ch1", "disabled by config"
        )

    if config.get("run_image_primitives", True):
        reporter.run("image_primitives", _probe_image_primitives)
    else:
        reporter.skip("image_primitives", "disabled by config")

    if int(config.get("stability_seconds", 0)) > 0:
        reporter.run("stability", lambda: _probe_stability(device, config))
    else:
        reporter.skip("stability", "set stability_seconds to 1800 for soak test")

    report = reporter.finish()
    print("[phase0] report", report_path)
    print("[phase0] status", report["status"])
    return report
