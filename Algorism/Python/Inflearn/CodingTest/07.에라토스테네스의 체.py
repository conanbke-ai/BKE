# 소수(에라토스테네스 체)
'''
자연수 N이 입력되면 1부터 N까지의 소수의 개수를 출력하는 프로그램을 작성하세요. 
만약 20이 입력되면 1부터 20까지의 소수는 2, 3, 5, 7, 11, 13, 17, 19로 총 8개입니다.
제한시간은 1초입니다. 

▣ 입력설명
첫 줄에 자연수의 개수 N(2<=N<=200,000)이 주어집니다.

 ▣ 출력설명
첫 줄에 소수의 개수를 출력합니다.
'''

def sieve(n):
    prime = [True] * (n + 1)
    prime[0] = prime[1] = False

    # 2~n의 제곱근까지만 실행
    for i in range(2, int(n**0.5) + 1):
        if prime[i]:
            # i의 배수 제거
            for j in range(i*i, n+1, i):
                prime[j] = False

    return len([i for i, is_prime in enumerate(prime) if is_prime])

print(sieve(20))

'''
예시1)
def sieve_large_n(n):
    """
    n 이하의 모든 소수를 리스트로 반환하는 최적화 버전
    - 홀수만 체크하여 메모리 절약
    - 배수 체크 시작을 prime^2부터 하여 반복 최소화
    """
    if n < 2:
        return []

    prime_list = [2]  # 2는 미리 추가
    size = (n + 1) // 2  # 홀수만 체크, index i -> 실제 수 2*i + 1
    is_prime = [0] * size  # 0 = 소수 가능, 1 = 소수 아님

    for i in range(1, size):
        if is_prime[i] == 0:              # i번째 홀수가 소수라면
            prime = 2 * i + 1
            prime_list.append(prime)
            start = (prime * prime) // 2  # prime^2부터 배수 체크
            for j in range(start, size, prime):
                is_prime[j] = 1           # 소수가 아님 표시

    return prime_list

# 사용 예시
n = 100
primes = sieve_large_n(n)
print("소수 개수:", len(primes))
print("소수 리스트:", primes)
'''