import os

with open("temp/one.txt" , 'w') as file:
    print("File created!")
    file.write("Hello\n")
    file.write("World\n")
    print("Writing Done!")

with open("temp/one.txt" , 'r') as file:
    print()
    print("Reading..")
    print(file.read())

print("File closed!")
os.remove("temp/one.txt")
print("File removed!")
