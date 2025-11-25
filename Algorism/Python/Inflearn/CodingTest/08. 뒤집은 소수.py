# 뒤집은 소수
'''
N개의 자연수가 입력되면 각 자연수를 뒤집은 후, 그 뒤집은 수가 소수이면 그 수를 출력하는 프로그램을 작성하세요. 
예를 들어 32를 뒤집으면 23이고, 23은 소수이다. 그러면 23을 출력한다. 
단 910를 뒤집으면 19로 숫자화 해야 한다. 첫 자리부터의 연속된 0은 무시한다.
뒤집는 함수인 def reverse(x) 와 소수인지를 확인하는 함수 def isPrime(x)를 반드시 작성하여 프로그래밍 한다.

 ▣ 입력설명
첫 줄에 자연수의 개수 N(3<=N<=100)이 주어지고, 그 다음 줄에 N개의 자연수가 주어진다.
각 자연수의 크기는 100,000를 넘지 않는다.

 ▣ 출력설명
첫 줄에 뒤집은 소수를 출력합니다. 출력순서는 입력된 순서대로 출력합니다.
'''
# 뒤집는 함수
def reverse(x, mode='reverse'):
    """
    x : 정수 입력
    mode : 기능 선택
        'reverse'  -> 숫자 뒤집기
        'sort_desc' -> 내림차순 정렬 후 정수
        'digit_sum' -> 자리수 합
    """
    digits = list(map(int, str(x)))
    
    if mode == 'reverse':
        return int(str(x)[::-1])
    
    elif mode == 'sort_desc':
        return int(''.join(map(str, sorted(digits, reverse=True))))
    
    elif mode == 'digit_sum':
        return sum(digits)
    
    else:
        raise ValueError("mode는 'reverse', 'sort_desc', 'digit_sum' 중 하나여야 합니다.")

# 소수판별 함수
def isPrime(x):
    if x < 2:
        return False
    for i in range(2, int(x**0.5) + 1):
        if x % i == 0:   # 나누어떨어지면 소수가 아님
            return False
    return True

def solution(nums):
    
    primeList = []
    
    for num in nums:
        num = reverse(num)
    
        if isPrime(num):
            primeList.append(num)
            
    return primeList
    
print(solution([32, 55, 62, 3700, 250]))