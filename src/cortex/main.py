def main() -> None:
    import uvicorn

    uvicorn.run("cortex.api.app:app", host="0.0.0.0", port=8000)