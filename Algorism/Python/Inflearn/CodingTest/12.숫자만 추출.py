# 숫자만 추출
'''
문자와 숫자가 섞여있는 문자열이 주어지면 그 중 숫자만 추출하여 그 순서대로 자연수를 만듭니다. 
만들어진 자연수와 그 자연수의 약수 개수를 출력합니다.
만약 “t0e0a1c2h0er”에서 숫자만 추출하면 0, 0, 1, 2, 0이고 이것을 자연수를 만들면 120이 됩니다. 
즉 첫 자리 0은 자연수화 할 때 무시합니다.  
출력은 120를 출력하고, 다음 줄에 120의 약수의 개수를 출력하면 됩니다.
추출하여 만들어지는 자연수는 100,000,000을 넘지 않습니다.

 ▣입력설명
첫 줄에 숫자가 썩인 문자열이 주어집니다. 문자열의 길이는 50을 넘지 않습니다.

 ▣출력설명
첫 줄에 자연수를 출력하고, 두 번째 줄에 약수의 개수를 출력합니다.
'''

def solution(word):
    # 1) 숫자만 뽑아서 자연수 만들기
    num_str = ""
    for ch in word:
        if ch.isdigit():    # 숫자 문자만 골라서
            num_str += ch   # 문자열에 이어 붙이기

    number = int(num_str)   # 앞자리 0들은 int 변환하면서 자동으로 제거됨

    # 2) 약수 개수 세기
    cnt_divisor = 0
    i = 1
    while i * i <= number:
        if number % i == 0:
            cnt_divisor += 1        # i
            if i != number // i:    # 짝 약수 (number / i) 가 i와 다르면 하나 더
                cnt_divisor += 1
        i += 1

    return number, cnt_divisor


print(solution("g0en2Ts8eSoft"))  # (28, 6)
print(solution("t0e0a1c2h0er"))   # (120, 16)

'''
예시1)
def solution(word):
    # 1) 숫자만 추출해서 자연수 만들기
    num_str = ""
    for ch in word:
        if ch.isdigit():       # ch가 숫자 문자이면
            num_str += ch      # 문자열에 이어 붙이기

    number = int(num_str)      # "028" -> 28, "00120" -> 120

    # 2) 약수 개수 세기 (for + sqrt 방식)
    cnt_divisor = 0
    limit = int(number ** 0.5)

    for i in range(1, limit + 1):
        if number % i == 0:          # i가 약수라면
            cnt_divisor += 1         # i
            if i != number // i:     # 짝 약수가 i와 다르면(제곱수 아닐 때)
                cnt_divisor += 1     # number // i

    return number, cnt_divisor


print(solution("g0en2Ts8eSoft"))  # (28, 6)
print(solution("t0e0a1c2h0er"))   # (120, 16)

'''