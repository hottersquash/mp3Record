from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
import asyncio

async def get_current_song():
    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = manager.get_current_session()
    if session:
        info = await session.try_get_media_properties_async()
        print(f"{info.title} - {info.artist}")

asyncio.run(get_current_song())
