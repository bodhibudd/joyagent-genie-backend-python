from fastapi import APIRouter

data_router = APIRouter()


@data_router.get("/data/allModels")
async def allModels():
    result = dict()
    result["code"] = 200
    result["data"] = []

    return result
