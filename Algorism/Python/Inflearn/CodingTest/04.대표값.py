# 대표값
'''
N명의 학생의 수학점수가 주어집니다. N명의 학생들의 평균(소수 첫째자리 반올림)을 구하고, 
N명의 학생 중 평균에 가장 가까운 학생은 몇 번째 학생인지 출력하는 프로그램을 작성하세요.

평균과 가장 가까운 점수가 여러 개일 경우 먼저 점수가 높은 학생의 번호를 답으로 하고, 높은 점수를 가진 학생이 여러 명일 경우 그 중 학생번호가 빠른 학생의 번호를 답으로 합니다.

 ▣ 입력설명
첫줄에 자연수 N(5<=N<=100)이 주어지고, 두 번째 줄에는 각 학생의 수학점수인 N개의 자연수가 주어집니다. 
학생의 번호는 앞에서부터 1로 시작해서 N까지이다.

 ▣ 출력설명
첫줄에 평균과 평균에 가장 가까운 학생의 번호를 출력한다.
평균은 소수 첫째 자리에서 반올림합니다.
'''
import math
from decimal import Decimal, ROUND_HALF_UP

def solution(n, scores):
    
    # 성적 평균, 소수점 첫째자리 반올림
    # 일반적으로 round는 round-half-to-even 방식
    # decimal, HALFROUND_HALF_UP 사용해야 함
    # avg = round(sum(scores) / n) => avg = round((sum(scores) / n) + 0.5)
    avg = Decimal(sum(scores) / n).to_integral_value(rounding=ROUND_HALF_UP)
    
    # 학생 번호
    best_idx = 0
    # 점수는 항상 양수이므로 tie-break 조건(score가 더 높은 경우)에 대비해 처음 학생 점수가 반드시 갱신되도록 설정
    best_score = -1
    # 비교 가능한 가장 큰 값(무한대), 첫 반복에서 반드시 diff가 더 작아져서 갱신되도록 설정
    best_diff = float('inf')

    for i, score in enumerate(scores):
        diff = abs(score - avg)

        # 더 가까운 점수면 갱신
        if diff < best_diff:
            best_diff = diff
            best_score = score
            best_idx = i + 1

        # 거리 같으면 더 높은 점수 우선
        elif diff == best_diff and score > best_score:
            best_score = score
            best_idx = i + 1

    return avg, best_idx


print(solution(10, [45, 73, 66, 87, 92, 67, 75, 79, 75, 80]))