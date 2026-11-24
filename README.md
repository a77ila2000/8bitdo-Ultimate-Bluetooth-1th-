# 8BitDo Ultimate Bluetooth 1세대 — 실험 펌웨어 기록·패치 도구

**대상: 원래 Ultimate Bluetooth Controller, 모델 80NA + 원래 동봉 수신기.**
컨트롤러 공식 v1.11 / 수신기 공식 v1.04의 정확한 원본만 받습니다.
Ultimate 2, 2C, 별도 Ultimate 2.4G 모델에는 사용할 수 없습니다.

조작 중 버벅임·완전 꺼짐 조사에서 시작해 ADC·배터리 경고 수정, 2.4G 주기 실험,
GitHub 구현 비교, 자동 송신 계측, 최종 일반 통합본 복귀까지의 기록입니다.
**비공식 실험판입니다. 500Hz 달성, 물리 버튼 지연 개선량, 꺼짐 해결은 입증되지 않았습니다.**

## 다운로드·업데이트

[실험 릴리스](https://github.com/a77ila2000/8bitdo-Ultimate-Bluetooth-1th-/releases/tag/v0.1.3-experimental)의
`UltimateBT-Gen1-Experimental-Windows-x64.zip`을 받아 **압축을 전부 풀어** 사용합니다.
Windows 10/11 x64용이며 Python을 별도로 설치할 필요가 없습니다.

1. [업데이트·복구 안내](docs/UPDATING.ko.md)를 읽고 정확한 모델을 확인합니다.
2. `Create-Firmware.cmd`를 실행합니다. 공식 원본·제조사 업데이트 도구를 내려받아 해시를 확인하고 `output`에 펌웨어와 원복 파일을 만듭니다. 이 단계는 장치에 쓰지 않습니다.
3. 다른 8BitDo USB 장치를 모두 빼고 한 대씩 `Update.cmd`를 실행합니다. 최종 조합은 **2번 컨트롤러 enhanced + 3번 receiver IN2ms**입니다. 두 장치는 각각 업데이트해야 합니다.
4. 일반 재연결 후 입력·진동·충전·절전·게임을 확인합니다. 문제가 있으면 같은 도구의 **4/5번 공식 원복**을 선택합니다.

릴리스에는 제조사 펌웨어/DLL이 들어 있지 않습니다. 공개 패치 레시피와 직접 작성한 도구를 배포하며,
제조사 원본에서 실제 기록 가능한 DAT를 로컬 생성합니다. 원본 서버가 바뀌거나 해시가 다르면 중단합니다.
소스 ZIP에는 실행 파일이 없으므로 Python 3.10+에서 `python patcher.py prepare`를 사용하거나 Windows 빌드를 진행합니다.

## 들어 있는 수정

| 파일 | 내용 | 실물 확인 범위 |
|---|---|---|
| `controller-conservative.dat` | 최초 ADC 다섯 번째 정상 샘플 경계 + 배터리 경고 카운터 | 컨트롤러 2대 기록·재연결·짧은 USB 입력·셋톱 홈 확인 |
| `controller-timing.dat` | 위 수정 + 2.4G 위치의 2ms 계산 | 한 대 중간 시험본. 이력 재현 전용; 업데이트 메뉴에서 제외 |
| `controller-enhanced.dat` | 위 수정 + 시작 tick 기준 일정 + 변경된 스틱 활동 판정 | 두 대 전체 앱 재읽기 일치. A는2.4G, B는USB 물리 입력 확인 |
| `receiver-2ms.dat` | 활성 XInput IN USB interval 4→2, 관련 CRC 갱신 | 수신기 두 대 기록·Full-Speed12Mbps IN2/OUT8과2.4G 입력 확인 |
| `RESTORE-*.dat` | 수정 없는 공식 v1.11 / v1.04 | 공식 원본과 동일 해시. 사용자별 보정·페어링 백업 파일은 아님 |

배터리 **경고** 판정과 ADC 경계만 수정했습니다. 보호 회로·저전압 차단·전부 비정상 샘플의 기존 복구 경로를 끄지 않았습니다.
일정 변경은 뒤 스위치가 2.4G 위치일 때 직접 USB에도 적용됩니다. Bluetooth 위치에서는 기존 타이머 재등록 경로를 유지합니다.
Switch 2 깨우기·백버튼 리매핑 패치를 합친 펌웨어가 아닙니다.

## 실제 속도 결과

[Gamepadla의 기본 펌웨어 실측](https://gamepadla.com/8bitdo-ultimate-bluetooth-controller.html)은
동글·XInput·공식 v1.10에서 **197.33Hz**다(P82 #4686/#4687,2025-03-12).
이번 최종 시험의 생성률289.081Hz는 이 외부 기본 실측값보다 **수치상 약46.50% 높다**.
기본 실측보다 높은 갱신을 관측한 결과와, 직전 시험본 대비 추가 증가를 나누어 정리한다.

| 구분 | 빈도 | 측정 기준 |
|---|---:|---|
| 기본 펌웨어의 외부 실측 참고값 |197.33Hz| Gamepadla, 공식1.10, 동글 XInput, Prometheus82 |
| 이전2ms 통합 시험본 |244.745Hz| 이번 컨트롤러 내부 source 태그 생성 |
| 최종 일정 수정본 |289.081Hz| 같은 source 태그 방식 |

외부 기본값은 다른 펌웨어·장치·측정법의 자료다. 따라서46.50%는 **외부 참고값과의 수치 비교**이며
동일 조건에서 입증한 순정 대비 향상률이 아니다. 현재 v1.11 순정의 동일 태그 A/B 및 물리 버튼 지연 검증은 남아 있다.

컨트롤러 내부에서 임시 순번·tick 태그를 만들고 실제 수신기→Windows에서 받았습니다.
아래 비교는 **이미 2ms 시험을 적용한 이전 통합본과 최종 일정 수정본의 두 순차 실행**입니다.
공식 순정 펌웨어와의 A/B 결과가 아닙니다.

| 측정 | 앞선 통합 시험 | 물리 스위치 조건 수정 후 |
|---|---:|---:|
| source 태그 생성 | 244.745Hz | 289.081Hz |
| Windows 태그 관측 | 244.745Hz | 288.970Hz |
| 관측 간격 중앙값 | 4.031ms | 3.849ms |
| p99 / 최대 간격 | 8.226 / 12.632ms | 8.131 / 10.647ms |
| PC에서 보이지 않은 source 번호 | 0 | 6 |
| 유효 구간 | 46.514초 | 54.410초 |

직전 시험본에서 최종 일정 수정까지 **추가18.12%** 차이를 관측했습니다. 기본197.33Hz 대비 증가율을 뜻하지 않습니다. 반복 무작위 A/B·물리 버튼 접점 지연 시험은 아니며,
6개 번호 공백의 원인을 전파 손실로 단정할 수 없습니다. USB 2ms 요청 기회와 새 입력 생성률은 서로 다릅니다.
임시 자동 입력 코드는 최종 배포 이미지에 없습니다. 일반 앱 105,472바이트 전체가 재읽기와 일치했고 뒤 512바이트는 FF임을 확인했습니다.

## 기록·검증·소스

- [처음부터 최종본까지 전체 작업 이력](docs/HISTORY.ko.md)
- [수정 위치·시간 계산·한계](docs/TECHNICAL.ko.md)
- [후속 성능 개선 비교와 실행 계획](docs/PERFORMANCE_PLAN.ko.md)
- [검증 수치와 남은 시험](docs/VALIDATION.ko.md), [공개 집계 자료](evidence/)
- [비교한 GitHub 프로젝트·공식 출처·라이선스](docs/SOURCES.md)
- [정확한 바이트 패치와 해시](patches/), [직접 작성한 Thumb 페이로드 소스](patch_source.py)
- [Windows 업데이트 어댑터 소스](windows/FlashTool.cs), [패치 생성기](patcher.py)

v0.1.2는 공식 updater의 `data` 하위 폴더를 누락했던 준비 오류를 고쳤습니다. 이전 준비 도구는 장치를 연결하면 쓰기 전에 종료될 수 있었습니다.
`Update.cmd`는 매번 준비 상태를 확인·복구하고, 어댑터도 폴더가 없으면 DLL 로드 전에 중단합니다.
수정된 공개 어댑터 경로로 두 번째 컨트롤러에 실제 기록100%·전체 앱 재읽기·USB 물리 입력을 확인했습니다.
이제 컨트롤러 두 대 모두 enhanced지만 속도 태그 시험은 첫 번째 한 대의 결과입니다. [두 번째 장치 검증](evidence/controller-b-final-validation.json).
v0.1.3은 실제 수신기의 CRC 없는 command8 응답을 정확한 모델6008/길이/주소/상태 조건으로 구분합니다.
컨트롤러의 기존 CRC 검사는 유지합니다. 공개 수신기 identity preflight와 실제 기록은 두 번째 수신기에서도 통과했습니다.
두 번째 세트도 활성 IN2/OUT8과2.4G 입력을 확인했습니다. [수신기 검증](evidence/receiver-b-final-validation.json).
확인을 건너뛰거나 모델을 강제로 맞추는 기능은 없습니다.

### 소스로 재현

```powershell
python patcher.py prepare
python -m pip install -r requirements-dev.txt
python -m pytest -q
# 이미 받은 원본만 사용
python patcher.py build --stock-dir cache --out output --offline
# Windows 실행 파일 빌드 (Python3.11 x64, .NET Framework4 compiler)
pwsh -File windows/build.ps1
```

원본·생성 이미지·개인 장치 덤프는 Git에 포함하지 않습니다. 직접 작성한 코드/문서는 MIT,
동봉한 8cryptdo는 해당 MIT 고지를 유지합니다. 제조사 펌웨어·업데이터의 권리는 제조사에 있습니다.

---

**English:** Experimental, exact-image patch recipes for the original **80NA Ultimate Bluetooth Controller**, controller1.11 / receiver1.04 only.
The Windows release downloads and verifies official originals, generates flashable DATs and official restore files locally,
and uses an adapter around the unmodified manufacturer's file-update API. No manufacturer firmware/DLL is redistributed.
Observed source-tag rate changed from244.7 to289.1Hz in two sequential instrumented trials, not from a stock baseline.
Gamepadla's external stock1.10 dongle/XInput reference is197.33Hz. Our final number is numerically46.50% higher;
different firmware and methods mean this is not a controlled stock-to-patched gain. The18.12% figure compares our two trials.
500Hz, physical button latency improvement and the original power-off symptom's resolution are unproven.
Injected measurement tags are absent from the final normal image. Read the Korean update/recovery guide before writing.
