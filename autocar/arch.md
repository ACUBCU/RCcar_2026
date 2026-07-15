flowchart TD
    Start((Start / Loop)) --> GetLidar[라이다 데이터 수집 및 보정]
    GetLidar --> Filter[노이즈 필터링 및 구역별 최소 거리 계산]
    Filter --> CheckCritical{전방 긴급 막힘?\n(front_dist < 350?)}

    %% 1. BACKING_UP 상태 처리
    CheckCritical -->|Yes| StateBackup[상태: BACKING_UP\n강제 후진 시작]
    CheckCritical -->|No| CheckState{현재 상태 확인}

    StateBackup --> BackupTimer{후진 0.5초 경과\nAND\n전방 70cm 확보?}
    BackupTimer -->|Yes 또는 최대 1.5초 경과| StateAlign[상태: ALIGNING 전환]
    BackupTimer -->|No| MoveBackward[액션: 후진 유지 (BACKWARD)]
    MoveBackward --> EndLoop((End Loop))

    %% 상태 분기
    CheckState -->|BACKING_UP 중| BackupTimer
    CheckState -->|INIT| StateInit[상태: INIT]
    CheckState -->|ALIGNING| CheckAlign[상태: ALIGNING\n좌회전 중]
    CheckState -->|FOLLOWING| CheckFollow[상태: FOLLOWING\n벽 타기 중]

    %% 2. INIT 상태 처리
    StateInit --> InitFrontCheck{전방 60cm 막힘?\n(front_dist < 600?)}
    InitFrontCheck -->|Yes| AlignStart[상태: ALIGNING 전환]
    InitFrontCheck -->|No| MoveForwardInit[액션: 직진 탐색 (FORWARD)]
    MoveForwardInit --> EndLoop

    %% 3. ALIGNING 상태 처리
    CheckAlign --> AlignClearCheck{전방 60cm 확보됨?\n(front_dist >= 600?)}
    AlignClearCheck -->|No| MoveTurnLeftAlign[액션: 좌회전 유지 (TURN_LEFT)]
    AlignClearCheck -->|Yes| AlignRightCheck{우측/대각선 1m 이내에\n벽 발견?}
    
    AlignRightCheck -->|Yes| FollowStart[상태: FOLLOWING 전환]
    AlignRightCheck -->|No| AlignLostCheck{전/우측 모두\n1.2m 이상 뚫림?}
    
    AlignLostCheck -->|Yes| InitStart[상태: INIT 전환 (벽 잃음)]
    AlignLostCheck -->|No| MoveTurnLeftAlign2[액션: 좌회전 유지 (TURN_LEFT)]

    MoveTurnLeftAlign --> EndLoop
    MoveTurnLeftAlign2 --> EndLoop

    %% 4. FOLLOWING 상태 처리
    CheckFollow --> FollowGapCheck{우측 틈새/코너 발견?\n(right_dist > 1000?)}
    
    FollowGapCheck -->|Yes| GapFrontCheck{코너 진입 중\n전방 40cm 막힘?}
    GapFrontCheck -->|Yes| AlignStart2[상태: ALIGNING 전환\n(충돌 회피)]
    GapFrontCheck -->|No| MoveSharpRight[액션: 우측 틈새 진입 (SHARP_RIGHT)]
    
    FollowGapCheck -->|No| FollowFrontCheck{일반 주행 중\n전방 60cm 막힘?}
    FollowFrontCheck -->|Yes| AlignStart3[상태: ALIGNING 전환]
    FollowFrontCheck -->|No| FollowPanicCheck{우측 벽과 18cm 이내?\n(패닉 충돌 임계치)}

    FollowPanicCheck -->|Yes| MoveSharpLeft[액션: 긴급 좌측 회피 (SHARP_LEFT)]
    FollowPanicCheck -->|No| FollowAdjustCheck{우측 목표 거리(40cm) 유지 확인}

    FollowAdjustCheck -->|> 55cm| MoveForwardRight[액션: 미세 우측 접근 (FORWARD_RIGHT)]
    FollowAdjustCheck -->|< 25cm| MoveForwardLeft[액션: 미세 좌측 회피 (FORWARD_LEFT)]
    FollowAdjustCheck -->|25~55cm| MoveForward[액션: 안정 직진 (FORWARD)]

    MoveSharpRight --> EndLoop
    MoveSharpLeft --> EndLoop
    MoveForwardRight --> EndLoop
    MoveForwardLeft --> EndLoop
    MoveForward --> EndLoop
    AlignStart --> MoveTurnLeftAlign
    AlignStart2 --> MoveTurnLeftAlign
    AlignStart3 --> MoveTurnLeftAlign
    InitStart --> MoveForwardInit
    FollowStart --> MoveForward