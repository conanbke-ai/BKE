# 주사위 게임

'''
1에서부터 6까지의 눈을 가진 3개의 주사위를 던져서 다음과 같은 규칙에 따라 상금을 받는 게임이 있다.
규칙(1) 같은 눈이 3개가 나오면 10,000원+(같은 눈)*1,000원의 상금을 받게 된다. 
규칙(2) 같은 눈이 2개만 나오는 경우에는 1,000원+(같은 눈)*100원의 상금을 받게 된다. 
규칙(3) 모두 다른 눈이 나오는 경우에는 (그 중 가장 큰 눈)*100원의 상금을 받게 된다.  
예를 들어, 3개의 눈 3, 3, 6이 주어지면 상금은 1,000+3*100으로 계산되어 1,300원을 받게 된다. 
또 3개의 눈이 2, 2, 2로 주어지면 10,000+2*1,000 으로 계산되어 12,000원을 받게 된다. 
3개의 눈이 6, 2, 5로 주어지면 그 중 가장 큰 값이 6이므로 6*100으로 계산되어 600원을 상금으로 받게 된다.
 N 명이 주사위 게임에 참여하였을 때, 가장 많은 상금을 받은 사람의 상금을 출력하는 프로그램을 작성하시오.

▣입력설명
첫째 줄에는 참여하는 사람 수 N(2<=N<=1,000)이 주어지고 그 다음 줄부터 N개의 줄에 사람들이 주사위를 던진 3개의 눈이 빈칸을 사이에 두고 각각 주어진다. 

▣출력설명
첫째 줄에 가장 많은 상금을 받은 사람의 상금을 출력한다.
'''

def solution(personList):
    
    cnt = 0
    cntList = {}
    award = []
    
    for person in personList:
        
        for p in person:
            if person.count(p) > cnt:
                cnt = person.count(p)
                cntList[p] = person.count(p)
                
        cnt = 0
                
    for n, c in cntList.items():
        if c == 3:
            award.append(10000 + 1000*n)
        elif c == 2:
            award.append(1000 + 100*n)
        elif c == 1:
            award.append(100*n)
    
    return max(award)

print(solution([[3, 3, 6], [2, 2, 2], [6, 2, 5]]))

'''
예시1)
from collections import Counter

def solution(personList):

    awards = []

    for person in personList:
        # person = [3,3,6] → counts = Counter({3:2, 6:1})
        counts = Counter(person)  # 각 숫자의 등장 횟수
        # 가장 많이 나온 숫자와 등장 횟수 튜플 반환 → 리스트에서 첫 번째 튜플 꺼내기((1)만 할 경우 [(튜플)] 형태이므로, 언패킹 불가능)
        most_common_num, most_common_count = counts.most_common(1)[0]  # 가장 많이 나온 숫자와 횟수

        if most_common_count == 3:        # 같은 눈 3개
            prize = 10000 + most_common_num * 1000
        elif most_common_count == 2:      # 같은 눈 2개
            prize = 1000 + most_common_num * 100
        else:                             # 모두 다른 눈
            prize = max(person) * 100

        awards.append(prize)

    return max(awards)
'''
