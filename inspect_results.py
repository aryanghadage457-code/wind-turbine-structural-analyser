import pickle

with open("out/res_G.pkl", "rb") as f:
    result = pickle.load(f)

print("Result type:", type(result))

if hasattr(result, "__dict__"):
    print("\nAvailable result fields:")

    for key, value in vars(result).items():
        if hasattr(value, "shape"):
            print(key, value.shape)
        else:
            print(key, type(value))
else:
    print(result)