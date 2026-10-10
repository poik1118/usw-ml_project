# data/high_diamond_ranked_10min.csv — 열 목록

**League of Legends Diamond Ranked Games (10 min)** · 다이아 I~마스터 솔로랭크
**9,879경기 × 40열 · 결측치 0건 · `blueWins` 49.9%** (완전 균형)

게임 시작 **정확히 10분 시점의 스냅샷**이다. AI에게 코드를 시킬 때 **이 목록의 열 이름만** 쓴다.

```bash
# 재다운로드
python -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/jppoter/Project-on-high_diamond_ranked_10min-dataset/main/high_diamond_ranked_10min.csv','high_diamond_ranked_10min.csv')"
```

## 구조

`gameId` + `blueWins` + **blue\* 19열 / red\* 19열 거울 구조** = 40열.

| 열 (blue\*/red\* 쌍) | 뜻 | 범위 |
|---|---|---|
| `blueWins` | **정답 열.** 1 = 블루 승 | 0 / 1 |
| `gameId` | 경기 ID. **모델에 넣지 않는다** | — |
| `blueGoldDiff` | 상대와의 골드 차 | -10,830 ~ +11,467 |
| `blueExperienceDiff` | 경험치 차 | -9,333 ~ +8,348 |
| `blueTotalGold` | 총 골드 | 10,730 ~ 23,701 |
| `blueGoldPerMin` | 분당 골드 = `blueTotalGold` / 10 | — |
| `blueTotalExperience` | 총 경험치 | — |
| `blueAvgLevel` | 평균 레벨 | 4.6 ~ 8.0 |
| `blueKills` / `blueDeaths` / `blueAssists` | 킬 · 데스 · 어시 | 0 ~ 22 |
| `blueFirstBlood` | 퍼블 획득 | 0 / 1 (양팀 합 항상 1) |
| `blueDragons` | 드래곤 | 0 / 1 |
| `blueHeralds` | 전령 | 0 / 1 |
| `blueEliteMonsters` | 드래곤 + 전령 **합** | 0 ~ 2 |
| `blueTowersDestroyed` | 철거한 포탑 | 0 ~ 4 (**95.3%가 0**) |
| `blueTotalMinionsKilled` | CS | 90 ~ 283 |
| `blueCSPerMin` | 분당 CS = `blueTotalMinionsKilled` / 10 | — |
| `blueTotalJungleMinionsKilled` | 정글 CS | 0 ~ 92 |
| `blueWardsPlaced` | 와드 설치 | 5 ~ 250 |
| `blueWardsDestroyed` | 와드 제거 | 0 ~ 23 |

## 중복 열 경고 — 40열 중 실질 정보는 11개다

전 행에서 다음이 성립한다. **40열을 그대로 모델에 넣으면 완전 공선성으로 계수가 무의미해진다.**

```
redGoldDiff          == -blueGoldDiff
redExperienceDiff    == -blueExperienceDiff
blueDeaths           == redKills
redDeaths            == blueKills
blueCSPerMin         == blueTotalMinionsKilled / 10
blueGoldPerMin       == blueTotalGold / 10
blueEliteMonsters    == blueDragons + blueHeralds
blueFirstBlood + redFirstBlood == 1
```

## 모델이 쓰는 차이 피처 11개

`core.fit_engine()`이 이 11개를 만들어 학습한다. **CV AUC 0.8106.**

| 피처 | 만드는 식 | raw 계수 부호 |
|---|---|---|
| `goldDiff` | `blueGoldDiff` | 양수 |
| `expDiff` | `blueExperienceDiff` | 양수 |
| `killDiff` | `blueKills - blueDeaths` | **음수** |
| `csDiff` | `blueTotalMinionsKilled - redTotalMinionsKilled` | **음수** |
| `jungleDiff` | `blueTotalJungleMinionsKilled - redTotalJungleMinionsKilled` | **음수** |
| `dragDiff` | `blueDragons - redDragons` | 양수 (최대) |
| `heraldDiff` | `blueHeralds - redHeralds` | 양수 |
| `towerDiff` | `blueTowersDestroyed - redTowersDestroyed` | **음수** |
| `wardDiff` | `blueWardsPlaced - redWardsPlaced` | 음수 (≈0) |
| `wardKillDiff` | `blueWardsDestroyed - redWardsDestroyed` | 양수 (≈0) |
| `firstBlood` | `blueFirstBlood * 2 - 1` (−1/+1 대칭화) | 양수 |

**음수 4개는 버그가 아니다.** 셋 다(`kill`·`cs`·`tower`) 골드의 대리변수라서, 골드차를
통제하면 "같은 골드인데 타워를 깼다 = 타워 말고는 다 밀렸다"가 되어 부호가 뒤집힌다.
단독 상관은 전부 양수다. 게임은 이 음수를 숨기지 않고 그대로 쓴다.

## 캡의 근거 — 임의 조정이 아니라 모델의 정의역

데이터에 `dragDiff`는 **-1 ~ +1만** 존재한다. 2를 입력하는 것은 모델이 본 적 없는 질문이다.

```
축 캡 (99분위):  goldDiff ±6,585   expDiff ±5,213
단위 캡 (관측 최대): killDiff 17 · towerDiff 4 · dragDiff 1 · heraldDiff 1
                    firstBlood 1 · csDiff 127 · jungleDiff 72 · wardDiff 260 · wardKillDiff 23
```

## 출처

Kaggle `bobbyscience/league-of-legends-diamond-ranked-games-10-min` (2020).
