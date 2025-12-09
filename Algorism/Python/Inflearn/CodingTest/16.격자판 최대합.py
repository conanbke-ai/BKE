# 격자판 최대합
'''
5*5 격자판에 아래롸 같이 숫자가 적혀있습니다. 
 10 13 10 12 15
 12 39 30 23 11
 11 25 50 53 15
 19 27 29 37 27
 19 13 30 13 19
 N*N의 격자판이 주어지면 각 행의 합, 각 열의 합, 두 대각선의 합 중 가 장 큰 합을 출력합
니다.

 ▣입력설명
첫 줄에 자연수 N이 주어진다.(1<=N<=50) 
두 번째 줄부터 N줄에 걸쳐 각 줄에 N개의 자연수가 주어진다. 각 자연수는 100을 넘지 않는
다. 

 ▣출력설명
최대합을 출력합니다.
'''
matrix = [
    [10, 13, 10, 12, 15],
    [12, 39, 30, 23, 11],
    [11, 25, 50, 53, 15],
    [19, 27, 29, 37, 27],
    [19, 13, 30, 13, 19],
]

def solution(matrix):
    
    result = []
    sum = 0
    
    # 각 행의 합
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            sum += matrix[i][j]
        result.append(sum)
        sum = 0
        
    # 각 열의 합
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            sum += matrix[j][i]
        result.append(sum)
        sum = 0
    
    # 두 대각선의 합
    for i in range(len(matrix)):
        sum += matrix[i][i]
    result.append(sum)
    sum = 0
        
    for i in range(len(matrix)):
        sum += matrix[len(matrix) - i - 1][i]
    result.append(sum)
    sum = 0
            
    return max(result)

print(solution(matrix))

'''
예시)
def solution(matrix):
    n = len(matrix)
    
    # 행, 열 최대
    max_sum = 0
    for i in range(n):
        row_sum = sum(matrix[i])
        col_sum = sum(matrix[j][i] for j in range(n))
        max_sum = max(max_sum, row_sum, col_sum)

    # 두 대각선
    diag1 = sum(matrix[i][i] for i in range(n))
    diag2 = sum(matrix[i][n - i - 1] for i in range(n))
    max_sum = max(max_sum, diag1, diag2)

    return max_sum
'''