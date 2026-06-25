import time
from functools import wraps


def runtime_check():
    def simple_rapper_inner(func):
        @wraps(func)
        def wrapper(*args, **kargs):
            ptime = time.time()
            result = func(*args, **kargs)
            end_time = time.time()
            print(f"실행 시간은 {end_time-ptime:.2f} s 입니다.")
            return result
        return wrapper
    return simple_rapper_inner


@runtime_check()
def simple_plus(n, s):
    for _ in range(n):
        s += 1
    return s


def main():
    re = simple_plus(50_000_000, 10_000_000)
    print(re)


if __name__ == "__main__":
    main()