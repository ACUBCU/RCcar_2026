class A_list:
    def __init__(self):
        self.myVariable = "A"
        self.myVariable2 = "a"
        self.A_list()
from pathlib import Path
import datetime
import json
import webview

now = datetime.datetime.now()

arr = [[0] for _ in range(3)]
l = len(arr)

dict_a = {"a" : 0, "b" : 1}

# with open("./python/code/week1/test_dict.json", "w", encoding='utf-8') as f:
#         json.dump(dict_a, f, ensure_ascii=False, indent=4)

webview.create_window(
        "simple text",
        url=(Path(__file__).resolve().parent / "text.html").as_uri(),
        width=640,
        height=520,
        resizable=True
        )
webview.start()