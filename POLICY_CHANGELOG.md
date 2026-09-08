# TORI Policy Changelog

Owner: TORI_COMMON

## 기록 방법

새 규칙은 기존 문서의 필요한 절을 수정하고 이곳에 한 변경 묶음으로 기록한다. 문서마다 복제본·새 final pack을 발행하지 않는다.

```text
Change-ID:
Class: PATCH | MINOR | MAJOR
Urgency: NORMAL | EMERGENCY_SECURITY
Affected tags / repos:
Summary:
Effective checkpoint:
In-flight handling:
Required action:
Approval / evidence:
```

발행 commit은 이 파일의 해당 변경이 들어간 Git commit으로 식별한다. 문서 안에 자기 commit SHA를 추정해 쓰지 않는다.

## 2026-09-08 — GOV-POLICY-DELIVERY-01

Class: MINOR
Urgency: NORMAL
Affected tags: POLICY, COORDINATION, SECURITY_REVIEW, RELEASE
Affected repos: 공통 정책을 참조하는 전체 프로젝트

- 기존 제품 AGENTS가 이미 참조하는 DEVELOPMENT_TEAM_OPERATING_POLICY 경로를 유지하고 bootstrap/router로 연결한다.
- 정책은 TORI_COMMON이 관리하고 BKE가 Git 게시처가 된다. Project 메모리를 정책 파일 자동 동기화 수단으로 가정하지 않는다.
- Policy baseline SHA와 code/PR SHA를 분리한다. 새 세션·위험 상승·인계·병합에서 관련 부분만 확인하고, 같은 작업의 동일 근거는 재사용한다.
- 진행 중 workstream은 일반 정책 문구 변경 때문에 중단·재시작하지 않는다. 미기록 baseline은 추정하지 않고 다음 checkpoint에 기록한다.
- security 기준과 router를 실제 BKE 경로에 게시한다. 제품 보안 검증 완료를 선언하는 작업은 아니다.
- 단일 작성자/lease 인계, 실제 ref 개수, 리뷰 SHA, 정책 접근 실패 및 수신 확인의 의미를 명확히 한다.

Effective checkpoint: 다음 새 세션 또는 기존 workstream의 정상 인계/통합 checkpoint.
In-flight handling: 기존 작업과 업로드 파일을 유지한다. 새 ZIP 업로드/Project Instructions 재복사를 요구하지 않는다. 기존에 요구된 더 엄격한 보안·통합 gate는 유지한다.
Required action: 담당 세션이 기존 AGENTS 참조를 읽을 때 새 진입점과 필요한 정책 절만 확인한다. 실제 정책 수신은 확인 전까지 PENDING이다.
Approval / evidence: 사용자가 반복 복사·정책 재독·작업 중단 부담을 줄이도록 보완을 요청한 이 대화. 제품 코드·배포 설정·결제·다른 작업의 branch/lease 변경은 포함하지 않는다.

## 긴급 알림

이 정책 게시 작업에서 새 EMERGENCY_SECURITY 알림을 발행하지 않았다. 이는 세 제품에 취약점이 없다는 진단이 아니다. 실제 코드 감사는 별도 작업이다.
