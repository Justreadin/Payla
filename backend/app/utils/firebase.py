import asyncio
from functools import partial


async def firestore_run(fn, *args, **kwargs):
    """
    Run blocking Firestore SDK calls safely in async code.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(fn, *args, **kwargs)
    )
