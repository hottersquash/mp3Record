import subprocess
import time
import re
import os
import threading
import queue

from winrt.windows.media import MediaPlaybackStatus

FFMPEG_PATH = "ffmpeg.exe"  # 确保 ffmpeg.exe 在当前目录或 PATH 中
RECORD_DURATION = 3600  # 最长录制时长防止死锁，单位秒
OUTPUT_DIR = "recordings"
os.makedirs(OUTPUT_DIR, exist_ok=True)
# 设置你的虚拟音频设备名称（从 ffmpeg -list_devices true -f dshow -i dummy 获取）
DEVICE_NAME = "CABLE Output (VB-Audio Virtual Cable)"
# FFmpeg 静音分轨参数
SILENCE_THRESH = "-30dB"  # 静音判断阈值
MIN_SILENCE_DURATION = 5  # 3 秒以上静音认为是切歌
# 音频编码参数
AUDIO_CODEC = "libmp3lame"
BITRATE = "320k"
PLAYER_PROCESS_NAMES = ["QQMusic.exe", "cloudmusic.exe", "KuGou.exe"]  # 可添加更多

import re

from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
import asyncio

def get_current_song_info_sync():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _inner():
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session:
            info = await session.try_get_media_properties_async()
            status = session.get_playback_info().playback_status
            return info.title + " - " + info.artist + ".mp3", status
        else:
            return None, None

    result = loop.run_until_complete(_inner())
    loop.close()
    return result


def enqueue_output(stderr, q):
    for line in iter(stderr.readline, b''):
        decoded = line.decode("utf-8", errors="ignore")
        q.put(decoded)
    stderr.close()


def monitor_silence(proc, stop_callback):
    q = queue.Queue()
    silent_since = None
    t = threading.Thread(target=enqueue_output, args=(proc.stderr, q))
    t.daemon = True
    t.start()

    while True:
        try:
            line = q.get(timeout=1)  # 等待最多1秒获取新日志行
        except queue.Empty:
            pass  # 没有新日志也继续执行下面的逻辑
        else:
            print("[ffmpeg]", line.strip())
            if "silence_start" in line:
                silent_since = time.time()
            else:
                silent_since = None

        if silent_since and (time.time() - silent_since > MIN_SILENCE_DURATION):
            print("⏹️ 检测到连续静音，自动停止录音。")
            stop_callback()

        if proc.poll() is not None:
            break  # ffmpeg 进程已退出

def start_recording(output_path):
    cmd = [
        FFMPEG_PATH,
        "-f", "dshow",
        "-i", f"audio={DEVICE_NAME}",
        "-af", f"silencedetect=noise={SILENCE_THRESH}:d=1",
        "-c:a", AUDIO_CODEC,
        "-b:a", BITRATE,
        "-t", str(RECORD_DURATION),
        "-y",
        output_path
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
    return proc
    # threading.Thread(target=monitor_silence, args=(proc, lambda: proc.terminate()), daemon=True).start()
    # return proc

def get_audio_duration(file_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(output)
    except Exception as e:
        print(f"⚠️ 无法获取时长：{e}")
        return 0

def main_loop():
    last_title = None
    process = None
    current_filename = ""

    while True:
        title, status = get_current_song_info_sync()
        if title and title != last_title:
            if process :
                print(f"🎵 结束录制：{last_title}")
                process.terminate()
                process.wait()
                duration = get_audio_duration(current_filename)
                if duration < 60:
                    print(f"🗑️ 文件过短（{duration:.1f}s），删除：{current_filename}")
                    os.remove(current_filename)

            current_filename = os.path.join(OUTPUT_DIR, title)
            if not os.path.exists(current_filename):
                print(f"▶️ 开始录制：{title}")
                process = start_recording(current_filename)
                last_title = title
            else:
                print(f"▶️ {title} 文件存在，跳过")
        time.sleep(2)

try:
    # 🟡 在主程序入口前调用
    # restart_as_admin()
    print("🎧 正在监听播放器，准备录制...")
    main_loop()
except KeyboardInterrupt:
    print("🛑 用户中断，退出程序。")
