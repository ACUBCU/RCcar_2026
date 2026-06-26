class Parent:
    def __init__(self, value):
        self.value = "부모 데이터"
        self.value2 = value
        print("Parent 클래스의 __init__ 메소드가 호출 되었습니다")

    def test(self):
        print("Parent 클래스의 test 메소드 입니다.")


class Child(Parent):
    def __init__(self):     # 부모 클래스의 __init__ overrideing
        # Parent.__init__(self, "자식에서 넘어간 값")
        super().__init__("자식에서 넘어간 값")
        print("Child 클래스의 __init__ 메소드가 호출 되었습니다")
        self.value = "자식 데이터"

    def test(self):     # 같은 이름의 메소드는 overriding 된다
        print("Child 클래스의 test 메소드 입니다.")


def main():
    p = Parent("first")
    p.test()
    print(p.value)
    print(p.value2)
    c = Child()
    c.test()
    print(c.value)
    print(c.value2)
    # print(c.value3)


if __name__ == "__main__":
    main()