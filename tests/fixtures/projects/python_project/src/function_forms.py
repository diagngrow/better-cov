def top():
    def nested():
        return 1
    return nested()

class Worker:
    def run(self):
        return 2

async def wait():
    return 3
