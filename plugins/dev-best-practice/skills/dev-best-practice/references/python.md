# Python 배치 판정

`common.md`의 판정을 전제하고, Python 저장소에만 적용되는 것을 담는다.

1. 배포하는 패키지는 `src/` 아래에 둔다
2. 밖에 내지 않을 것은 밑줄 접두로 표시한다
3. 패키지 루트 `__init__.py`만 공개 API로 쓴다
4. 파일 이름은 snake_case로 쓴다
5. `utils.py`는 패키지마다 하나까지 둔다

판정의 근거는 실제로 운영되는 저장소를 센 결과다. 2026-09-04에 GitHub `git/trees` API로 아래 열넷의 파일 경로를 받아 세었다(`tests`, `docs`, `examples`, `benchmarks`, `scripts` 경로 제외).

pydantic, fastapi, flask, requests, rich, textual, httpx, pip, poetry, httpie, scrapy, celery, litestar, typer

## 1. 배포하는 패키지는 `src/` 아래에 둔다

**flat layout에서는 작업 디렉토리의 소스가 설치본을 가린다.** 저장소 루트에서 실행하면 `sys.path`의 맨 앞이 작업 디렉토리라, `mypkg/`가 루트에 있으면 설치된 것이 아니라 그 폴더를 읽는다. 재현해 확인했다(Python 3.14, 2026-09-04).

```text
flat   (mypkg/ 가 루트에)      import된 것 → 작업 디렉토리의 소스
src/   (src/mypkg/)           import된 것 → site-packages의 설치본
```

패키징이 빠뜨린 파일이 있어도 flat에서는 테스트가 통과한다. 설치본으로 도는지 확인하려면 `src/`가 필요하다.

- 열넷 중 다섯이 쓴다 — flask, requests, textual, pip, poetry. 나머지 아홉은 flat이다(pydantic, fastapi, rich, httpx, httpie, scrapy, celery, litestar, typer).
- **설치해서 쓰지 않는 것에는 안 써도 된다.** 서비스와 스크립트처럼 저장소에서 바로 실행하는 것은 위 문제가 생기지 않는다. 라이브러리와 CLI처럼 배포하는 것에만 적용한다.

## 2. 밖에 내지 않을 것은 밑줄 접두로 표시한다

Go의 `internal/`에 해당하는 자리다. 강제되지 않고 관례이지만 실측에서 널리 쓰인다.

| 저장소 | 밑줄 접두 파일 / 전체 | 밑줄 접두 폴더 |
|---|---|---|
| textual | 119 / 240 | - |
| pip | 59 / 360 | `_internal`, `_vendor` |
| pydantic | 32 / 99 | `_internal` |
| httpx | 15 / 21 | `_transports` |
| litestar | 20 / 254 | `_asgi`, `_kwargs`, `_layers`, `_openapi`, `_signature` |
| typer | 8 / 30 | `_click` |
| scrapy | 8 / 156 | - |

세는 규칙은 이렇다 — 전체는 패키지 아래 `.py` 중 `__init__.py`를 뺀 수이고, 밑줄 접두 파일은 그중 이름이 밑줄 하나로 시작하는 것이다(`__`로 시작하는 것은 빼고, `tests`, `docs`, `examples`, `benchmarks`, `scripts` 경로도 뺐다).

httpx가 극단이다 — 파일 21개 중 15개가 `_`로 시작하고 공개하는 이름은 전부 `__init__.py`가 낸다. 안을 어떻게 바꾸든 쓰는 쪽이 안 깨진다.

**폴더에도 같은 접두를 쓴다.** `_internal/`은 그 아래 전부가 내부라는 뜻이고, pip은 의존성까지 `_vendor/`로 감싼다.

## 3. 패키지 루트 `__init__.py`만 공개 API로 쓴다

`react.md` 판정 4는 배럴 파일을 앱 코드에 두지 않는다고 정한다. **Python의 패키지 루트 `__init__.py`는 예외다** — 배포 경계라 밖에서 부르는 이름을 여기서 정해야 한다. `react.md`가 판정 대상을 앱 코드로 한정한 것과 같은 선이고, 하위 폴더의 `__init__.py`에는 그 판정이 그대로 걸린다.

| 저장소 | 루트 `__init__.py` 줄 | `from .` 줄 | `__all__` 원소 | 지연 import |
|---|---|---|---|---|
| pydantic | 457 | 21 | 151 | 있음 |
| requests | 220 | 8 | 25 | 없음 |
| textual | 208 | 0 | 4 | 있음 |
| celery | 177 | 1 | 15 | 없음 |
| httpx | 107 | 13 | 70 | 없음 |
| flask | 40 | 39 | - | 없음 |
| typer | 34 | 27 | - | 없음 |
| fastapi | 26 | 19 | - | 없음 |

**하위 폴더의 `__init__.py`는 비워 둔다.** 실측에서 하위 `__init__.py` 대부분이 0바이트이거나 80바이트 미만이다(celery 46개 중 33개, poetry 36개 중 18개, litestar 63개 중 24개). 여기서 재export를 시작하면 `react.md` 판정 4가 적은 비용을 그대로 문다.

**`__all__`이 크면 지연 import를 검토한다.** pydantic은 `__all__` 원소가 151개라 모듈 전부를 미리 읽지 않으려고 `__getattr__`로 이름을 부를 때 읽는다. textual도 같다. `__all__`이 수십 개를 넘어가면 이 비용이 생긴다.

## 4. 파일 이름은 snake_case로 쓴다

열넷 전부에서 대문자가 든 `.py` 파일이 0개였다. 클래스 하나만 담은 모듈도 `text_area.py`이고 `TextArea.py`가 아니다.

파일 이름이 곧 import 경로이므로 `common.md` 판정 3이 그대로 걸린다 — 이름은 다루는 대상을 가리킨다.

## 5. `utils.py`는 패키지마다 하나까지 둔다

`common.md` 판정 3은 `utils.py` 같은 파일을 피하라고 한다. 실측은 그 이름이 널리 쓰인다고 나온다 — 열넷 중 열에 있고, fastapi에 4개, httpie에 4개, litestar에 8개다.

**어디에 있는지가 갈린다.** `common.md`가 경고하는 것은 여러 곳이 함께 쓰는 서랍이지 패키지 하나에 붙은 지역 도우미가 아니다. 실측한 파일이 전부 지역 도우미인 것은 아니다 — `fastapi/security/utils.py`는 `fastapi/security/`만 쓰지만, `fastapi/openapi/utils.py`는 `fastapi/applications.py`가 `from fastapi.openapi.utils import get_openapi`로 부르고 `litestar/_openapi/utils.py`는 `litestar/openapi/config.py`가 부른다(2026-09-04 확인). 이름이 `utils.py`라는 것만으로는 갈리지 않으므로, 아래 규칙으로 판정한다.

- **한 패키지에 `utils.py`를 하나까지 둔다.** `utils.py`와 `helpers.py`와 `common.py`를 같은 폴더에 함께 두지 않는다.
- **다른 패키지에서 import하기 시작하면 그때 나눈다.** 그 시점에 대상 이름 모듈로 옮긴다.
- **`utils/` 폴더로 커지면 `common.md` 판정 3의 폴더 판정을 적용한다** — 안이 다시 대상별로 나뉘면 괜찮고, `utils/misc.py`처럼 다시 서랍을 만들면 고친다. scrapy에 `scrapy/utils/misc.py`가 그 형태로 있다.
