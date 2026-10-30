// 04 IA 보드 재작성 + 07 멀티 소스 구조 보드 신규. use_figma(code) 또는 Scripter로 실행.
const FAM='Noto Sans KR';
const F=s=>({family:FAM,style:s});
await Promise.all(['Regular','Medium','Bold'].map(s=>figma.loadFontAsync(F(s))));
const page=await figma.getNodeByIdAsync('112:2');
await figma.setCurrentPageAsync(page);
const removed=[];
for(const c of [...page.children]){if(c.type==='SECTION'&&c.name.startsWith('04 ')){removed.push(c.id);c.remove();}}
const hex=h=>{const n=parseInt(h.slice(1),16);return{r:((n>>16)&255)/255,g:((n>>8)&255)/255,b:(n&255)/255}};
const solid=(h,o)=>{const p={type:'SOLID',color:hex(h)};if(o!==undefined)p.opacity=o;return p};
const ids=[];
function text(str,o={}){const {size=14,style='Regular',color='#1F1F1F',w,align='LEFT',lh}=o;const t=figma.createText();t.fontName=F(style);t.characters=str;t.fontSize=size;t.fills=[solid(color)];if(lh)t.lineHeight={unit:'PIXELS',value:lh};t.textAlignHorizontal=align;if(w){t.resize(w,10);t.textAutoResize='HEIGHT';}return t;}
function label(parent,str,x,y,o={}){const t=text(str,o);t.x=x;t.y=y;parent.appendChild(t);return t;}
function box(parent,o){const {x,y,w,h,fill='#FFFFFF',stroke='#D9D9D9',sw=1,r=8,name='box'}=o;const f=figma.createFrame();f.name=name;f.resize(w,h);f.x=x;f.y=y;f.fills=fill?[solid(fill)]:[];f.strokes=stroke?[solid(stroke)]:[];f.strokeWeight=sw;f.cornerRadius=r;f.clipsContent=false;parent.appendChild(f);return f;}
function card(parent,o){const {x,y,w,h,title,sub,fill='#FFFFFF',stroke='#D9D9D9',titleColor='#1F1F1F',subColor='#666666',r=10,name,tsize=15,ssize=12,align='CENTER'}=o;const f=box(parent,{x,y,w,h,fill,stroke,r,name:name||title});f.layoutMode='VERTICAL';f.primaryAxisSizingMode='FIXED';f.counterAxisSizingMode='FIXED';f.resize(w,h);f.primaryAxisAlignItems='CENTER';f.counterAxisAlignItems='CENTER';f.paddingLeft=12;f.paddingRight=12;f.itemSpacing=4;const t=text(title,{size:tsize,style:'Bold',color:titleColor,align});f.appendChild(t);t.layoutSizingHorizontal='FILL';t.textAutoResize='HEIGHT';if(sub){const s=text(sub,{size:ssize,color:subColor,align,lh:ssize+5});f.appendChild(s);s.layoutSizingHorizontal='FILL';s.textAutoResize='HEIGHT';}return f;}
function seg(parent,x1,y1,x2,y2,o={}){const {color='#8A8A8A',dash=false,head=true}=o;const pad=8;const minx=Math.min(x1,x2)-pad,miny=Math.min(y1,y2)-pad,w=Math.abs(x2-x1)+pad*2,h=Math.abs(y2-y1)+pad*2;const ax=x1-minx,ay=y1-miny,bx=x2-minx,by=y2-miny;let hd='';const s=8,hw=4.5;if(head){if(x2>x1)hd=`M${bx} ${by} L${bx-s} ${by-hw} L${bx-s} ${by+hw} Z`;else if(x2<x1)hd=`M${bx} ${by} L${bx+s} ${by-hw} L${bx+s} ${by+hw} Z`;else if(y2>y1)hd=`M${bx} ${by} L${bx-hw} ${by-s} L${bx+hw} ${by-s} Z`;else hd=`M${bx} ${by} L${bx-hw} ${by+s} L${bx+hw} ${by+s} Z`;}
const svg=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg"><path d="M${ax} ${ay} L${bx} ${by}" stroke="${color}" stroke-width="2" fill="none"${dash?' stroke-dasharray="6 5"':''}/>${hd?`<path d="${hd}" fill="${color}"/>`:''}</svg>`;const n=figma.createNodeFromSvg(svg);n.name=head?'arrow':'line';n.x=minx;n.y=miny;parent.appendChild(n);return n;}
function section(name,x,y,w,h){const s=figma.createSection();s.name=name;s.x=x;s.y=y;s.resizeWithoutConstraints(w,h);s.fills=[solid('#F7F7F5')];page.appendChild(s);ids.push(s.id);return s;}
function bullets(parent,x,y,w,items,o={}){const {size=12,lh=18,color='#333333'}=o;return label(parent,items.map(i=>'• '+i).join('\n'),x,y,{size,lh,color,w});}

// ===== 04 IA (v2, 메뉴 10개) =====
let S=section('04 관리자 정보 구조(IA) · 기능 정의 (v2 멀티 소스)',4680,0,2400,1240);
label(S,'04 관리자 정보 구조(IA) · 기능 정의',40,32,{size:28,style:'Bold'});
label(S,'v2: 소스 관리 · 카테고리 매핑 · 주문 관리 · 시스템 설정 메뉴가 추가됨 (12개). 설정은 관리자 웹에서, 승인은 텔레그램에서. 등록은 엑셀 산출까지만.',40,78,{size:14,color:'#555555'});
card(S,{x:1000,y:130,w:400,h:70,title:'auto-store 관리자 웹',sub:'로컬 웹 · 단일 계정 로그인 (.env) · FastAPI + HTMX',fill:'#1F2933',stroke:null,titleColor:'#FFFFFF',subColor:'#CBD2D9'});
const menus=[['대시보드',false,['소스별 배치 결과 요약','상태별 상품 수','오류 · 차단 목록 (소스별)','카테고리 확인 대기 건수','수동 실행 (수집 / 알림)']],['소스 관리',true,['사이트 등록 · 수정 · 중지','국가 · 통화 · base URL','어댑터 종류 선택\n  내장 / 범용 CSS / LLM 추출','범용 CSS 셀렉터 입력','로그인 프로필 저장 (브라우저)','요청 지연 · 하루 상한 · 차단 허용','배송 프로필 지정','1페이지 테스트 수집','헬스 (마지막 성공 · 연속 실패)']],['카테고리 매핑',true,['표준 카테고리 트리 관리','네이버 코드 · 품목 유형 · 기본 무게','별칭 사전 (언어별 표기)\n  과자 = 스넥 = 零食 = お菓子','속성 별칭 (玻璃 = ガラス = glass)','LLM 제안 확인 대기 큐\n  승인 / 다른 카테고리 / 거절']],['수집 카테고리',false,['소스별 목록 URL 등록','표준 카테고리 매핑 (사전 추천)','수집 페이지 수','사용 on / off','소스 × 카테고리 매트릭스']],['제외 규칙',false,['재질 / 품목 유형 / 키워드 /\n  브랜드 로고 탭','정규화 코드 기준 (언어 무관)','품목 요건 3단계\n  제외 / 요건 필요 / 통과','브랜드 로고 감지(비전 LLM)\n  → 자동 제외 on / off','거절 이력 기간 (기본 90일)','코드별 발견 상품 수 (소스별)']],['비용 설정',false,['환율 (통화별 자동 / 고정)','배송 프로필 탭 (경로별)\n  요율표 · 현지 배송비 · 배송일','관세율 · 부가세율','네이버 · 결제 수수료','목표 마진율 · 통관 경고 구간']],['매칭 설정',false,['국내 가격 방식\n  (평균 / 중앙값 / 최저가)','상위 N · 정확 임계값 · 유사 하한','하루 후보 수 (기본 10)','후보 점수 가중치\n  마진 · 경쟁 · 수요 · 리스크','동일 이미지 판매자 상한 (5곳)','데이터랩 수요 기간 (3개월)']],['콘텐츠 설정',false,['상품명 키워드 조합 규칙 (50자)','옵션 표준 사전 (색상 · 사이즈 · 용량)','고지문 · 배송기간 · 반품 정책 블록','이미지 모드 A (B / C는 개선)','금지 문구 목록','상세페이지 템플릿 선택']],['상품 목록',false,['상단 "URL 즉시 분석" 입력창','즉시 분석 이력 탭\n  (이전 결과 · 재분석 · 비교)','소스 · 상태 · 카테고리 필터','원가 내역 (통화 · 배송 프로필)','경쟁 · 수요 · 리뷰 숫자 · 매칭 근거','정확 / 유사 매칭 결과','생성 이미지 미리보기','재시도 · 수동 승인 · 폐기 · 승인 이력','"등록 완료" 표시\n  (스토어 상품번호 · 판매가)','감시 탭: 마지막 점검 · 변동 이력']],['주문 관리',true,['주문 목록 (상태별)','주문 ↔ 소스 상품 · 옵션 · 원가 ·\n  배대지 한 화면','체크리스트: 통관부호 → 소스 주문\n  → 입고 → 발송 → 통관 → 완료','예상 도착일 (소스 주문일 + 배송일)','실제 원가 입력 (결제액 · 수수료 ·\n  배대지 · 관부가세)','예상 vs 실제 원가 차이','월 손익 요약 탭']],['실행 로그',false,['소스별 단계 기록','건수 (수집 / 제외 / 매칭 / 차단)','오류 상세 (스택)','셀렉터 실패 감지 알림','LLM 호출 건수 · 비용']],['시스템 설정',true,['AI 제공자 선택\n  Claude / Gemini / OpenAI','텍스트 LLM · 이미지 생성 각각','모델 · API 키 · 연결 테스트','API 월 예산 · 경고 비율\n  · 초과 시 동작','배치 스케줄\n  수집 시각 · 알림 시각 · 요일','등록 상품 감시 주기 ·\n  가격 변동 임계값','배치 미실행 경고','이미지 스토리지 (Supabase)\n  URL · 키 · 버킷','텔레그램 봇 토큰 · chat_id','관리자 비밀번호 변경']]];
const MW=176,GAP=16,X0=40;const xc=i=>X0+i*(MW+GAP)+MW/2;
seg(S,1200,200,1200,251);seg(S,xc(0),252,xc(11),252,{head:false});
menus.forEach((m,i)=>{const x=X0+i*(MW+GAP);seg(S,xc(i),252,xc(i),299);card(S,{x,y:300,w:MW,h:56,title:m[0],fill:m[1]?'#FFE4C4':'#DDEBFF',stroke:m[1]?'#C05621':'#2B6CB0',tsize:14});if(m[1]){const nb=box(S,{x:x+MW-44,y:292,w:40,h:18,fill:'#C05621',stroke:null,r:9,name:'NEW'});label(nb,'NEW',0,2,{size:10,style:'Bold',color:'#FFFFFF',w:40,align:'CENTER'});}const b=box(S,{x,y:372,w:MW,h:330,fill:'#FFFFFF',stroke:m[1]?'#C05621':'#D0D0D0',r:10,name:m[0]+' 기능'});bullets(b,12,12,MW-24,m[2],{size:11,lh:17});});
const extra=[['텔레그램 봇 기능','#DDEBFF','#2B6CB0',['08:00 요약: 소스별 수집 / 차단 · 제외 · 후보 · 카테고리 확인 대기 건수','1차 후보 카드: 소스 배지 · 원가(통화) · 국내 비교가 · 마진율 · 매칭 수 · 플래그','같은 상품이 여러 소스에 있으면 "다른 소스 비교 → 최저" 한 줄 추가','[승인] [거절] [보류] → 승인 즉시 ⑥⑦ 백그라운드 실행','2차 미리보기 카드 · [패키지 생성] [수정 요청] [폐기]','수정 요청 → 메모 한 줄 → ⑦ 재실행','보류 → 다음날 알림에 다시 포함','URL 즉시 분석: 상품 URL을 보내면 1~2분 내 같은 카드로 응답 · /recent 로 최근 이력','예산 경고(80%) · 예산 초과로 ⑦ 중단 · 배치 미실행 · 소스 차단 알림','⑩ 등록 상품 변동 카드: 가격 ±임계값 · 품절 · 옵션 품절 · 최소수량 · 삭제\n  [판매가 수정] [판매 중지] [무시]']],['배치 스케줄 · 운영 규칙','#EEF0F4','#4A5568',['수집 시각(기본 02:00)  ① 소스별 수집 → ② 정규화 → ③ 매칭 → ④ 원가 계산','소스마다 Playwright 프로필 · 지연 · 상한 · 차단 허용을 따로 둔다','차단은 소스 단위로 당일 중단, 다른 소스는 계속','브랜드 로고 감지 상품은 brand_detected로 자동 제외','표준 카테고리를 모르는 상품은 mapping_pending으로 멈추고 확인 후 재개','알림 시각(기본 08:00)  ⑤ 마진율순 상위 N건(기본 10) 카드 발송','⑦ 실행 전 월 예산 잔여 확인 · 초과 시 중단하고 알림','⑩ 감시: 설정 주기(기본 3일)로 listed 상품 소스 재점검, 수집 직후 실행','Windows 작업 스케줄러로 앱 자동 시작 · 실패 단계는 error → 재시도']],['등록 패키지 산출물 (⑨)','#D9F2E3','#2F855A',['생성 이미지를 Supabase Storage(공개 버킷)에 업로드 → 공개 URL','output/YYYY-MM-DD/naver_bulk_upload.xlsx 에 행 추가 (이미지 칸 = 공개 URL)','네이버 "상품 일괄등록" 양식 컬럼 준수','로컬 사본 output/YYYY-MM-DD/<소스>_<상품ID>/','판매가 = 총원가 ÷ (1 − 목표 마진율), 100원 단위 올림','구매대행 고지 블록: 소스 국가와 배송 프로필의 배송일 반영','추후 커머스 API 자동 등록 시 이 행이 입력 데이터']]];
extra.forEach((e,i)=>{const x=40+i*780;const b=box(S,{x,y:760,w:750,h:440,fill:e[1],stroke:e[2],r:12,name:e[0]});label(b,e[0],20,16,{size:17,style:'Bold'});bullets(b,20,52,710,e[3],{size:13,lh:22});});

// ===== 07 멀티 소스 구조 =====
S=section('07 멀티 소스 구조 · 표기 정규화',4680,1360,2000,1000);
label(S,'07 멀티 소스 구조 · 표기 정규화',40,32,{size:28,style:'Bold'});
label(S,'사이트는 관리자가 등록하고, 어댑터가 원시 데이터만 뽑으며, 정규화기가 통화·언어·카테고리·속성을 하나의 표준으로 맞춘다. ③ 이후는 소스가 무엇이든 동일.',40,78,{size:14,color:'#555555'});
const srcs=[['1688','CN · CNY · 내장'],['타오바오','CN · CNY · 내장'],['알리익스프레스','CN · USD · 내장'],['NETSEA','JP · JPY · 범용 CSS'],['슈퍼딜리버리','JP · JPY · 범용 CSS'],['사용자 등록 사이트','국가 · 통화 · 어댑터 선택']];
srcs.forEach((s,i)=>{const y=140+i*72;card(S,{x:40,y,w:200,h:56,title:s[0],sub:s[1],fill:i===5?'#FFE4C4':'#FFFFFF',stroke:i===5?'#C05621':'#A0A0A0',tsize:13,ssize:11});seg(S,240,y+28,290,y+28,{head:false});});
seg(S,290,168,290,528,{head:false});
const ads=[['내장 어댑터','코드로 작성\nselectors/<key>.yaml',205],['범용 CSS 어댑터','관리자가 셀렉터 입력\n1페이지 테스트 후 저장',345],['LLM 추출 어댑터','Claude 구조화 추출\n→ 셀렉터 제안 → 승격',485]];
ads.forEach(a=>{card(S,{x:330,y:a[2]-45,w:220,h:90,title:a[0],sub:a[1],fill:'#EEF0F4',stroke:'#4A5568',tsize:14});seg(S,290,a[2],329,a[2]);seg(S,550,a[2],590,a[2],{head:false});});
seg(S,590,205,590,485,{head:false});seg(S,590,345,619,345);
card(S,{x:620,y:250,w:220,h:190,title:'RawListing (원시 데이터)',sub:'item_id · url\ntitle_raw · lang\nprice_raw · currency · moq\nimage_url · category_raw\nattrs_raw · weight_raw',fill:'#FFFFFF',stroke:'#A0A0A0',tsize:13,ssize:12});
seg(S,840,345,909,345);
card(S,{x:910,y:220,w:250,h:250,title:'② 정규화기 (Normalizer)',sub:'통화 → 원화 (소스 환율)\n언어 감지 → 한국어 검색어\n재질·품목 → 코드 (attribute_aliases)\n카테고리 → 표준 (category_aliases)\n모르는 표기 → LLM 제안 → 확인 큐\n브랜드 로고 감지 → 자동 제외\n제외 규칙 적용 (코드 기준)',fill:'#DDEBFF',stroke:'#2B6CB0',tsize:14,ssize:12});
seg(S,1160,345,1229,345);
card(S,{x:1230,y:250,w:220,h:190,title:'표준 상품 (products)',sub:'source_id + source_item_id\ncanonical_category_id\nprice_krw · currency · moq\nmaterial_code · item_type\ntitle_ko · product_group_id',fill:'#FFFFFF',stroke:'#4A5568',tsize:13,ssize:12});
seg(S,1450,345,1529,345);
card(S,{x:1530,y:290,w:240,h:110,title:'③ 매칭 → ④ 원가 → ⑤ 알림',sub:'소스가 무엇이든 동일한 파이프라인\n원가는 소스의 배송 프로필 사용',fill:'#D9F2E3',stroke:'#2F855A',tsize:13,ssize:12});
label(S,'소스 (관리자 등록)',40,112,{size:12,style:'Bold',color:'#555555'});label(S,'어댑터 (3종)',330,112,{size:12,style:'Bold',color:'#555555'});
const ex=box(S,{x:40,y:600,w:1100,h:370,fill:'#FFFFFF',stroke:'#D0D0D0',r:12,name:'표기 차이 흡수 예시'});
label(ex,'표기 차이 흡수 예시 · 표준 카테고리 "식품 > 과자"',20,14,{size:16,style:'Bold'});
card(ex,{x:440,y:150,w:220,h:84,title:'식품 > 과자',sub:'naver 500xxxxx · item_type food\n→ 목록통관 배제 → 자동 제외',fill:'#1F2933',stroke:null,titleColor:'#FFFFFF',subColor:'#CBD2D9',tsize:15,ssize:11});
const L=[['과자','ko · seed'],['스넥','ko · manual'],['스낵류','ko · llm 0.92'],['snack','en · seed']];const R=[['零食','zh · seed'],['膨化食品','zh · llm 0.81'],['休闲食品','zh · llm 0.77'],['お菓子','ja · seed'],['スナック','ja · manual']];
L.forEach((p,i)=>{const y=60+i*58;card(ex,{x:60,y,w:200,h:44,title:p[0]+'  ('+p[1]+')',fill:'#F1F1EE',stroke:'#A0A0A0',tsize:12,r:22});seg(ex,260,y+22,350,y+22,{head:false});});
seg(ex,350,82,350,256,{head:false});seg(ex,350,192,439,192);
R.forEach((p,i)=>{const y=50+i*54;card(ex,{x:800,y,w:220,h:44,title:p[0]+'  ('+p[1]+')',fill:'#F1F1EE',stroke:'#A0A0A0',tsize:12,r:22});seg(ex,800,y+22,750,y+22,{head:false});});
seg(ex,750,72,750,288,{head:false});seg(ex,750,192,661,192);
label(ex,'속성도 같은 방식: 玻璃 · ガラス · 유리 · glass → material = glass. 코드 기준이라 소스가 늘어도 제외 규칙 · 네이버 매핑 · 원가 계산은 하나다. 사전에 없는 표기는 LLM 제안 → 관리자 승인 → 사전 추가.',20,322,{size:12,color:'#555555',w:1060,lh:18});
const pr=box(S,{x:1180,y:600,w:780,h:370,fill:'#FFFBE6',stroke:'#E0C76A',r:12,name:'새 사이트 붙이는 절차'});
label(pr,'새 사이트 붙이는 절차 (코드 없이)',20,14,{size:16,style:'Bold',color:'#8A6D00'});
['1  소스 등록: 이름 · 국가 · 통화 · 어댑터 종류 · 배송 프로필 · 요청 정책','2  로그인 필요 시 "브라우저 열기"로 1회 수동 로그인 → 프로필 저장','3  수집 카테고리 등록: 목록 URL + 표준 카테고리 매핑 (별칭 사전이 추천)','4  "1페이지 테스트 수집"으로 RawListing 확인 (범용 CSS면 셀렉터 조정)','5  활성화 → 다음 새벽 배치부터 포함'].forEach((s,i)=>label(pr,s,20,48+i*26,{size:13,color:'#5A4A00'}));
label(pr,'배송 프로필 (경로별 · 소스가 하나를 가리킴)',20,196,{size:14,style:'Bold',color:'#8A6D00'});
card(pr,{x:20,y:226,w:360,h:120,title:'중국 → 한국 배대지 A',sub:'CNY · 0.5kg 단위 요율표\n현지 배송비 기본 8 CNY · 평균 7~14일',fill:'#FFFFFF',stroke:'#C05621',tsize:13,ssize:12});
card(pr,{x:400,y:226,w:360,h:120,title:'일본 → 한국 배대지 B',sub:'JPY · 요율표 별도\n현지 배송비 기본 800 JPY · 평균 5~10일',fill:'#FFFFFF',stroke:'#C05621',tsize:13,ssize:12});

// ===== 08 등록 상품 감시 =====
for(const c of [...page.children]){if(c.type==='SECTION'&&c.name.startsWith('08 ')){removed.push(c.id);c.remove();}}
S=section('08 등록 상품 감시 (⑩)',6980,1360,1700,1000);
label(S,'08 등록 상품 감시 (⑩)',40,32,{size:28,style:'Bold'});
label(S,'스토어에 올린 상품의 소스가 품절·가격 변동·삭제되면 고객 결제 후 못 사는 사고가 난다. 설정한 주기로 소스를 재점검하고 변동만 알린다.',40,78,{size:14,color:'#555555'});
card(S,{x:40,y:150,w:220,h:90,title:'packaged',sub:'⑨ 엑셀 패키지 완료',fill:'#D9F2E3',stroke:'#2F855A',tsize:14,r:32});
seg(S,260,195,329,195);
card(S,{x:330,y:140,w:240,h:110,title:'관리자 "등록 완료" 표시',sub:'스토어 상품번호 · 판매가 입력\n→ listed (감시 대상)',fill:'#FFE4C4',stroke:'#C05621',tsize:14});
seg(S,570,195,639,195);
card(S,{x:640,y:130,w:280,h:130,title:'⑩ 감시기 (주기: 관리자 설정)',sub:'기본 3일마다 · 새벽 수집 직후\n소스 어댑터 detail 재수집\n요청 정책은 소스 설정 공유',fill:'#DDEBFF',stroke:'#2B6CB0',tsize:14});
seg(S,920,195,989,195);
card(S,{x:990,y:120,w:300,h:150,title:'변동 판정 → 원가 재계산',sub:'가격 ±임계값 (기본 5%) · 최소수량 변경\n전체 품절 · 등록 옵션 품절\n페이지 삭제(404) · 복구 감지\n임계값 미만 가격 변동은 기록만',fill:'#FFFFFF',stroke:'#4A5568',tsize:14});
seg(S,1140,270,1140,329);
label(S,'변동 있을 때만',1150,290,{size:12,color:'#555555'});
card(S,{x:990,y:330,w:300,h:90,title:'텔레그램 변동 카드',sub:'[판매가 수정] [판매 중지] [무시]',fill:'#DDEBFF',stroke:'#2B6CB0',tsize:14});
const dec=[['판매가 수정','새 원가로 목표 마진율 판매가 제안\n→ naver_price_update.xlsx 행','#D9F2E3','#2F855A'],['판매 중지','suspended\n→ naver_status_update.xlsx 행\n복구 감지 시 다시 알림','#FDECEC','#C53030'],['무시','이번 변동만 확인 처리\n다음 주기에 다시 비교','#F1F1EE','#A0A0A0']];
dec.forEach((d,i)=>{const x=740+i*270;card(S,{x,y:480,w:250,h:110,title:d[0],sub:d[1],fill:d[2],stroke:d[3],tsize:14});});
// 텔레그램 카드 → 가로 버스 → 결정 카드 3개
seg(S,1140,420,1140,450,{head:false});
seg(S,865,450,1405,450,{head:false});
[865,1135,1405].forEach(x=>seg(S,x,450,x,479));
// 텔레그램 카드 목업
const ph=box(S,{x:40,y:300,w:390,h:420,fill:'#D6E2EE',stroke:null,r:24,name:'휴대폰 · 변동 카드'});
const bub=box(ph,{x:16,y:20,w:358,h:380,fill:'#FFFFFF',stroke:null,r:12,name:'봇 말풍선'});
label(bub,'등록 상품 변동 3건 (10-30 02:40 점검)',12,12,{size:13,style:'Bold',w:334});
label(bub,'[1688 · 6912345678] 스테인리스 보온 텀블러 500ml\n가격 ¥18.5 → ¥21.8 (+18%) · 재계산 마진율 34% → 12%\n제안 판매가 23,900 → 27,900원',12,40,{size:12,color:'#333333',w:334,lh:18});
[['판매가 수정','#2F855A',12],['판매 중지','#C53030',128],['무시','#A0A0A0',244]].forEach(b=>{const bt=box(bub,{x:b[2],y:100,w:104,h:30,fill:b[1],stroke:null,r:8,name:'btn '+b[0]});label(bt,b[0],0,7,{size:12,style:'Medium',color:'#FFFFFF',w:104,align:'CENTER'});});
label(bub,'[타오바오 · 6912340077] 실리콘 접이식 도시락\n옵션 "그린" 품절 (나머지 2개 판매 중)',12,146,{size:12,color:'#333333',w:334,lh:18});
[['옵션 제외','#2F855A',12],['판매 중지','#C53030',128],['무시','#A0A0A0',244]].forEach(b=>{const bt=box(bub,{x:b[2],y:190,w:104,h:30,fill:b[1],stroke:null,r:8,name:'btn '+b[0]});label(bt,b[0],0,7,{size:12,style:'Medium',color:'#FFFFFF',w:104,align:'CENTER'});});
label(bub,'[NETSEA · 88123] 스테인리스 텀블러\n페이지 삭제됨 (404) · 소스에서 내려감',12,236,{size:12,color:'#C53030',w:334,lh:18});
[['판매 중지','#C53030',12],['다른 소스 찾기','#2B6CB0',128],['무시','#A0A0A0',244]].forEach(b=>{const bt=box(bub,{x:b[2],y:280,w:104,h:30,fill:b[1],stroke:null,r:8,name:'btn '+b[0]});label(bt,b[0],0,7,{size:12,style:'Medium',color:'#FFFFFF',w:104,align:'CENTER'});});
label(bub,'감시 실패 2건 (슈퍼딜리버리 로그인 만료) · 다음 점검 11-02',12,330,{size:11,color:'#999999',w:334,lh:16});
label(S,'텔레그램 변동 카드 예시',40,270,{size:12,style:'Bold',color:'#555555'});
const rules=box(S,{x:470,y:640,w:1190,h:320,fill:'#FFFBE6',stroke:'#E0C76A',r:12,name:'감시 규칙'});
label(rules,'감시 규칙 · 데이터',20,14,{size:16,style:'Bold',color:'#8A6D00'});
bullets(rules,20,48,560,['대상은 listed와 suspended(복구 감지용)만. 후보 단계 상품은 새벽 배치가 다시 수집한다','같은 상품의 같은 변동은 결정 전까지 다시 알리지 않는다','소스 차단 시 그 소스 감시는 건너뛰고 "감시 실패 N건"으로 요약','3회 연속 실패한 상품은 check_needed로 표시','감시 건수는 소스의 하루 수집 상한에 포함된다'],{size:13,lh:22});
bullets(rules,600,48,570,['listings: store_product_no · sale_price_krw · monitor_status · last_checked_at','monitor_events: kind(price / soldout / option_soldout / moq / removed / restored) · before / after · 재계산 마진율 · 결정','시스템 설정: 감시 주기(일) · 가격 변동 임계값(%) · "지금 점검" 버튼','상품 목록 감시 탭: 마지막 점검 · 변동 이력 · 결정 내역','스토어 반영은 1차에선 엑셀 행까지, 커머스 API 연동 시 자동'],{size:13,lh:22});

// ===== 09 운영 범위 (초기 운영 vs 운영 후 개선) =====
for(const c of [...page.children]){if(c.type==='SECTION'&&c.name.startsWith('09 ')){removed.push(c.id);c.remove();}}
S=section('09 운영 범위 · 초기 운영(MVP)과 운영 후 개선',8800,1360,1900,1000);
label(S,'09 운영 범위 · 초기 운영(MVP)과 운영 후 개선',40,32,{size:28,style:'Bold'});
label(S,'돌아가는 시스템이 먼저. 왼쪽이 끝까지 돌아간 뒤 실제 판매를 시작하고, 오른쪽은 판매 데이터를 보고 붙인다. (2026-10-30 확정)',40,78,{size:14,color:'#555555'});
const mvp=box(S,{x:40,y:120,w:1180,h:840,fill:'#F0FFF4',stroke:'#2F855A',r:12,name:'초기 운영 (MVP)'});
label(mvp,'초기 운영 (MVP)',20,16,{size:18,style:'Bold',color:'#2F855A'});
const rows=[['소싱','1688 · 알리익스프레스 내장 어댑터 · 범용 CSS 어댑터 · 수집 카테고리 · 거절 이력·중복 방지 · URL 즉시 분석(텔레그램·웹 입구, 이력 목록·재분석·이전 결과 비교)'],['상품성 판단','원가·마진율(대리구매 수수료 · 환차손 완충) · 경쟁 강도(정확 매칭 수 · 동일 이미지 판매자 수) · 데이터랩 수요 · 리뷰 수·판매 신호(실제 숫자) · 매칭 근거 · 하루 후보 수 N(기본 10, 설정)'],['리스크 검수','브랜드 로고·상표 자동 제외 · 품목 요건 3단계(제외 / 요건 필요 / 통과) · 150달러 경계 경고'],['등록','키워드 상품명 후보 · 네이버 카테고리 자동 추천 · 옵션 정리 · 고지문·배송기간·반품 블록 · 이미지 모드 A + 템플릿 · Supabase 업로드 · 엑셀'],['주문·배송','주문 처리 화면(주문 ↔ 소스 상품·옵션·원가·배대지) · 통관고유부호 체크리스트 · 예상 도착일'],['재고·가격','등록 상품 소스 감시(⑩): 품절 · 가격 · 옵션 · 최소수량 · 삭제'],['정산','주문별 실제 원가 기록 · 월 손익 요약'],['시스템','배치 스케줄 · 미실행 경고 · 소스 차단 알림 · 백업 · API 예산 · 텔레그램 2단계 승인 · 환율 자동 수집']];
rows.forEach((r,i)=>{const y=52+i*96;const t=box(mvp,{x:20,y,w:150,h:80,fill:'#FFFFFF',stroke:'#2F855A',r:8,name:r[0]});label(t,r[0],0,30,{size:14,style:'Bold',color:'#2F855A',w:150,align:'CENTER'});label(mvp,r[1],190,y+8,{size:13,color:'#1F1F1F',w:960,lh:20});});
const imp=box(S,{x:1260,y:120,w:600,h:840,fill:'#F7F7F5',stroke:'#A0A0A0',r:12,name:'운영 후 개선'});
label(imp,'운영 후 개선',20,16,{size:18,style:'Bold',color:'#555555'});
const irows=[['소싱','타오바오 · 일본 B2B · LLM 추출 어댑터 · 소스 간 그룹핑','1688·알리로 월 매출이 나면'],['상품성','정확도 프리셋 세분화 · 중앙값/최저가','오판 사례가 쌓이면'],['등록','이미지 모드 B / C · 커머스 API 자동 등록','잘 팔리는 상품이 생기면'],['재고·가격','환율 급변 재계산 알림 · 국내 경쟁가 추적',''],['CS','예상 도착일 자동 안내 · 답변 템플릿 봇','문의 하루 5건 넘으면'],['시스템','AI 제공자 다중 선택 · CLIP 로컬 · 회계 연동','처음엔 제공자 1개']];
irows.forEach((r,i)=>{const y=52+i*128;label(imp,r[0],20,y,{size:14,style:'Bold',color:'#555555'});label(imp,r[1],20,y+24,{size:13,color:'#333333',w:560,lh:20});if(r[2])label(imp,'넣을 때: '+r[2],20,y+70,{size:12,color:'#8A8A8A',w:560});});
return {removed,sectionIds:ids};
