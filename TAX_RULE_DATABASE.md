# 증여세 계산 규칙 DB 연동

FastAPI는 증여세 계산 시 `app/data`의 고정 세율·공제 데이터를 사용하지
않고 Mirizoom DB의 다음 테이블을 조회한다.

- `gift_deduction_limit`: 관계·미성년 여부별 10년 합산 공제 한도
- `gift_tax_bracket`: 과세표준 구간별 세율과 누진공제액

## 적용일 선택

- `facts.gift_date`가 `YYYY-MM-DD`로 있으면 해당 증여일을 사용한다.
- 증여일이 없으면 FastAPI 서버의 오늘 날짜를 사용한다.
- 적용 조건은 `effective_from <= 적용일`이고
  `effective_to IS NULL OR effective_to > 적용일`이다.
- `effective_to`는 다음 개정 시행일이므로 포함하지 않는다.
- 세율은 적용일에 유효한 버전 중 가장 최근 `effective_from` 버전을
  `lower_bound` 순서로 전부 조회한다.

## 관계 매핑

| FastAPI `relationship_type` | DB `relation` | `is_minor` |
|---|---|---:|
| `parent_to_adult_child` | `LINEAL_DESCENDANT` | `0` |
| `parent_to_minor_child` | `LINEAL_DESCENDANT` | `1` |
| `other_relative` | `OTHER` | `0` |
| `other` | `OTHER` | `0` |

현재 테이블 ENUM으로는 배우자와 직계존속을 별도 구분할 수 없다.
`spouse`, `child_to_parent`를 `OTHER`로 임의 계산하면 잘못된 공제가 적용될
수 있으므로 FastAPI는 계산 불가로 처리한다. 해당 관계도 지원하려면
`gift_deduction_limit.relation`에 별도 값을 추가해야 한다.

## 환경 변수

```dotenv
MIRIZOOM_DB_HOST=localhost
MIRIZOOM_DB_PORT=3306
MIRIZOOM_DB_NAME=miriZoom
MIRIZOOM_DB_USER=root
MIRIZOOM_DB_PASSWORD=your_password
MIRIZOOM_DB_CONNECT_TIMEOUT=5
```

## 오류 처리

유효한 공제 행이나 세율 버전이 없거나 DB 조회가 실패하면 고정값으로
대체 계산하지 않는다. 계산 실패 안내를 컨텍스트에 넣고 서버 로그에
`gift_tax.rule_or_calculation_failed`를 기록한다.
