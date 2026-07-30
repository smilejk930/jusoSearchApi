# jusoSearchApi

행정안전부 도로명주소 검색 API를 이용해 CSV의 주소를 조회하고, 도로명주소와
지번주소를 CSV로 저장하는 Python 스크립트입니다.

## 실행 환경

- Python 3.10 이상
- 도로명주소 검색 API 승인키

승인키는 [주소기반산업지원서비스](https://business.juso.go.kr/jst/jstRoadNmAddrApiSearch)에서
신청할 수 있습니다.

### Windows PowerShell

가상환경 사용을 권장합니다.



```powershell
cd jusoSearchApi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests
```

### macOS / Linux

```bash
cd jusoSearchApi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests
```

## API 승인키 설정

샘플 환경설정 파일을 `.env`로 복사합니다.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

생성된 `.env`에 발급받은 승인키를 입력합니다.

```dotenv
JUSO_API_KEY=발급받은_도로명주소_API_승인키
```

`.env`는 `.gitignore`에 등록되어 Git과 GitHub에 올라가지 않습니다. 실제
승인키를 `.env.example`이나 소스 코드에 입력하지 마세요.

## 입력 CSV

`addresses.csv.example`을 `addresses.csv`로 복사한 뒤 조회할 주소를 입력합니다.

Windows PowerShell:

```powershell
Copy-Item addresses.csv.example addresses.csv
```

macOS / Linux:

```bash
cp addresses.csv.example addresses.csv
```

입력 파일은 `pk`, `addrnm` 두 컬럼을 사용합니다. UTF-8 CSV를 권장하며 헤더가
없는 파일도 처리할 수 있습니다. 실제 `addresses.csv`는 Git에 포함되지 않습니다.

```csv
pk,addrnm
1,서울특별시 강남구 테헤란로 152
```

## 실행

입력 주소와 API 반환 도로명주소가 정확히 일치하지 않는 결과만 `result.csv`에
저장됩니다. 정확히 일치한 주소는 결과 파일에 기록되지 않습니다.

```bash
python jusoSearchApi.py --input addresses.csv
```

`result.csv`에는 유사결과, 검색결과 없음, API 오류 등 확인이 필요한 행만
남습니다. 결과 파일은 Git에 포함되지 않습니다. 파일명을 직접 지정하려면
`--output`을 사용합니다.

```bash
python jusoSearchApi.py --input addresses.csv --output custom_result.csv
```

승인키를 파일에 저장하지 않고 한 번만 지정하려면 `--api-key`를 사용합니다.

```bash
python jusoSearchApi.py --input addresses.csv --api-key "승인키"
```

## 실행 옵션

```text
--input              입력 CSV 경로 (필수)
--output             불일치 결과 CSV 경로 (생략 시 result.csv)
--api-key            이번 실행에서 사용할 API 승인키
--request-interval   서로 다른 주소 조회 사이의 대기 시간(초, 기본값 0.1)
--log-level          DEBUG, INFO, WARNING, ERROR 중 선택
```

호출 제한 오류가 반복될 경우 요청 간격을 늘릴 수 있습니다.

```bash
python jusoSearchApi.py \
  --input addresses.csv \
  --request-interval 0.5 \
  --log-level INFO
```

## 결과 CSV

결과 파일에는 다음 컬럼이 생성됩니다.

| 컬럼 | 설명 |
| --- | --- |
| `pk` | 입력 데이터 식별자 |
| `addrnm` | 입력 주소 |
| `조회성공` | 검색 결과 존재 여부 |
| `정확일치` | 입력 주소와 반환 도로명주소의 일치 여부 |
| `상태` | 정확일치, 유사결과, 검색결과없음 또는 오류 상태 |
| `반환도로명주소` | API가 반환한 도로명주소 |
| `반환지번주소` | API가 반환한 지번주소 |
| `오류코드` | API 또는 입력 오류 코드 |
| `오류메시지` | 오류 상세 메시지 |

동일한 입력 주소는 한 번만 API로 조회한 뒤 캐시된 결과를 재사용합니다. 일시적인
통신 오류와 API 호출 제한 오류(`E0007`)는 자동으로 재시도합니다.
