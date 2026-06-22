name = input("상품명 : ")
price = input("상품 가격 : ")
discount = input("할인율 : ")
if price.isdigit() and discount.isdigit():
    price = int(price)
    discount = int(discount)
    discounted_price = price * (100 - discount) / 100
    print(f"상품명 : {name}, 원래 가격 : {price}, 할인율 : {discount}%, 할인 금액 : {price - discounted_price}, 할인된 가격 : {discounted_price}")
else:
    print("숫자로 입력해야 합니다.")