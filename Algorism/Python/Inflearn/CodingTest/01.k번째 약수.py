# k번째 약수
# 첫째 줄에 N과 K가 빈칸을 사이에 두고 주어진다. N은 1이상 10,000이하이다. K는 1 이상 N 이하이다.
# 첫째 줄에서 N의 약수들 중 K번째로 작은 수를 출력한다. 만일 N의 약수의 개수가 K보다 작은 경우, -1 출력하시오.

def solution(num1, num2):
    
    divisor = []
    
    for i in range(1, num1 + 1):  # 0 제외
        if num1 % i == 0:
            divisor.append(i)

    if len(divisor) >= num2:  # 약수가 충분히 있을 때
        return divisor[num2 - 1]
    
    return -1  # 없으면 -1

print(solution(8, 4))  # 4번째 약수 → 8
