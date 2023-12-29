import os
import time

start = time.time()
with open("one.txt", "w") as file:
    for i in range(1000):
        file.write("Hello World")

with open("one.txt", "r") as file:
    for i in range(1000):
        file.readline()

os.remove("one.txt")
print("Total time for local File System:", (time.time() - start) * 10**3, "ms")

start = time.time()
with open("temp/one.txt", "w") as file:
    for i in range(1000):
        file.write("Hello World")

with open("temp/one.txt", "r") as file:
    for i in range(1000):
        file.readline()

os.remove("temp/one.txt")

print("Total time for cloud File System:", (time.time() - start) * 10**3, "ms")