# 정다면체

'''
두 개의 정 N면체와 정 M면체의 두 개의 주사위를 던져서 나올 수 있는 눈의 합 중 가장 확률이 높은 숫자를 출력하는 프로그램을 작성하세요.
정답이 여러 개일 경우 오름차순으로 출력합니다.

 ▣ 입력설명
첫 번째 줄에는 자연수 N과 M이 주어집니다. N과 M은 4, 6, 8, 12, 20 중의 하나입니다.

 ▣ 출력설명
첫 번째 줄에 답을 출력합니다.
'''

def solution(N, M):
    freq = dict()

    # 주사위 눈 합 계산
    for i in range(1, N + 1):
        for j in range(1, M + 1):
            s = i + j
            freq[s] = freq.get(s, 0) + 1

    # 가장 많이 나온 횟수
    max_cnt = max(freq.values())

    # 그 횟수를 가진 합(키)들을 오름차순으로 반환
    result = [k for k, v in freq.items() if v == max_cnt]
    
    return sorted(result)

print(solution(4, 6))