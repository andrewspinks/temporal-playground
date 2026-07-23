from temporalio import activity


@activity.defn
async def store_secret(secret: str) -> str:
    activity.logger.info(f"Storing secret of length {len(secret)}")
    return f"stored:{secret}"
