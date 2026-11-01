// 06 · DESIGN.md v3(2026-11-01) 반영: Supabase 단일 DB · 공용/개인 데이터 · 계정 로그인 · 발굴 우선 · AI 최소화.
//   재생성: 03 구성도 · 04 IA · 09 운영 범위 (섹션을 지우고 같은 자리에 v3 로 다시 그림)
//   신규:   10 데이터 모델(공용 vs 개인 · RLS) · 11 발굴 배치 ⓪~⑤ (AI 0회/건)
//   갱신:   01 프로세스 문구 + v3 띠 · 02 상태 머신 v3 메모 · 06 텔레그램 카드 문구
// Scripter 로 Page 3 에서 1회 실행. 실행 후 05 스크립트를 다시 돌려 "보드" 프레임으로 감싼다. 다시 돌리면 03·04·09 는 재생성, 10·11 은 중복되므로 1회만.
const FAM='Noto Sans KR';
const F=s=>({family:FAM,style:s});
await Promise.all(['Regular','Medium','Bold'].map(s=>figma.loadFontAsync(F(s))));
const getNode=async id=>figma.getNodeByIdAsync?await figma.getNodeByIdAsync(id):figma.getNodeById(id);
const page=await getNode('112:2');
if(figma.setCurrentPageAsync)await figma.setCurrentPageAsync(page);else figma.currentPage=page;
const hex=h=>{const n=parseInt(h.slice(1),16);return{r:((n>>16)&255)/255,g:((n>>8)&255)/255,b:(n&255)/255}};
const solid=(h,o)=>{const p={type:'SOLID',color:hex(h)};if(o!==undefined)p.opacity=o;return p};
const ids=[],removed=[],changed=[];
function text(str,o={}){const {size=14,style='Regular',color='#1F1F1F',w,align='LEFT',lh}=o;const t=figma.createText();t.fontName=F(style);t.characters=str;t.fontSize=size;t.fills=[solid(color)];if(lh)t.lineHeight={unit:'PIXELS',value:lh};t.textAlignHorizontal=align;if(w){t.resize(w,10);t.textAutoResize='HEIGHT';}return t;}
function label(parent,str,x,y,o={}){const t=text(str,o);t.x=x;t.y=y;parent.appendChild(t);return t;}
function box(parent,o){const {x,y,w,h,fill='#FFFFFF',stroke='#D9D9D9',sw=1,r=8,name='box'}=o;const f=figma.createFrame();f.name=name;f.resize(w,h);f.x=x;f.y=y;f.fills=fill?[solid(fill)]:[];f.strokes=stroke?[solid(stroke)]:[];f.strokeWeight=sw;f.cornerRadius=r;f.clipsContent=false;parent.appendChild(f);return f;}
function card(parent,o){const {x,y,w,h,title,sub,fill='#FFFFFF',stroke='#D9D9D9',titleColor='#1F1F1F',subColor='#666666',r=10,name,tsize=15,ssize=12,align='CENTER'}=o;const f=box(parent,{x,y,w,h,fill,stroke,r,name:name||title});f.layoutMode='VERTICAL';f.primaryAxisSizingMode='FIXED';f.counterAxisSizingMode='FIXED';f.resize(w,h);f.primaryAxisAlignItems='CENTER';f.counterAxisAlignItems='CENTER';f.paddingLeft=12;f.paddingRight=12;f.itemSpacing=4;const t=text(title,{size:tsize,style:'Bold',color:titleColor,align});f.appendChild(t);t.layoutSizingHorizontal='FILL';t.textAutoResize='HEIGHT';if(sub){const s=text(sub,{size:ssize,color:subColor,align,lh:ssize+5});f.appendChild(s);s.layoutSizingHorizontal='FILL';s.textAutoResize='HEIGHT';}return f;}
function seg(parent,x1,y1,x2,y2,o={}){const {color='#8A8A8A',dash=false,head=true}=o;const pad=8;const minx=Math.min(x1,x2)-pad,miny=Math.min(y1,y2)-pad,w=Math.abs(x2-x1)+pad*2,h=Math.abs(y2-y1)+pad*2;const ax=x1-minx,ay=y1-miny,bx=x2-minx,by=y2-miny;let hd='';const s=8,hw=4.5;if(head){if(x2>x1)hd=`M${bx} ${by} L${bx-s} ${by-hw} L${bx-s} ${by+hw} Z`;else if(x2<x1)hd=`M${bx} ${by} L${bx+s} ${by-hw} L${bx+s} ${by+hw} Z`;else if(y2>y1)hd=`M${bx} ${by} L${bx-hw} ${by-s} L${bx+hw} ${by-s} Z`;else hd=`M${bx} ${by} L${bx-hw} ${by+s} L${bx+hw} ${by+s} Z`;}
const svg=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg"><path d="M${ax} ${ay} L${bx} ${by}" stroke="${color}" stroke-width="2" fill="none"${dash?' stroke-dasharray="6 5"':''}/>${hd?`<path d="${hd}" fill="${color}"/>`:''}</svg>`;const n=figma.createNodeFromSvg(svg);n.name=head?'arrow':'line';n.x=minx;n.y=miny;parent.appendChild(n);return n;}
function section(name,x,y,w,h){const s=figma.createSection();s.name=name;s.x=x;s.y=y;s.resizeWithoutConstraints(w,h);s.fills=[solid('#F7F7F5')];page.appendChild(s);ids.push(s.id);return s;}
function bullets(parent,x,y,w,items,o={}){const {size=12,lh=18,color='#333333'}=o;return label(parent,items.map(i=>'• '+i).join('\n'),x,y,{size,lh,color,w});}
function badge(parent,x,y,str,fill,w){const ww=w||str.length*9+22;const b=box(parent,{x,y,w:ww,h:20,fill,stroke:null,r:10,name:str});label(b,str,0,3,{size:10,style:'Bold',color:'#FFFFFF',w:ww,align:'CENTER'});return b;}
const findSec=p=>page.children.find(c=>c.type==='SECTION'&&c.name.startsWith(p));
const holderOf=sec=>sec.children.find(c=>c.type==='FRAME'&&c.name==='보드')||sec;
async function regen(prefix,name,fx,fy,fw,fh,fallbackId){let old=findSec(prefix);if(!old&&fallbackId){const n=await getNode(fallbackId);if(n&&n.type==='SECTION')old=n;}let x=fx,y=fy,w=fw,h=fh;if(old){x=old.x;y=old.y;w=Math.max(old.width,fw);h=Math.max(old.height,fh);removed.push(old.name);old.remove();}return section(name,x,y,w,h);}
function retext(sec,map){for(const t of sec.findAllWithCriteria({types:['TEXT']})){const nv=map[t.characters];if(nv!==undefined){t.characters=nv;changed.push(t.id);}}}
const GREEN=['#D9F2E3','#2F855A'],BLUE=['#DDEBFF','#2B6CB0'],ORANGE=['#FFE4C4','#C05621'],GREY=['#EEF0F4','#4A5568'],YEL=['#FFFBE6','#E0C76A'];

// ===== 03 구성도 (v3) — 재생성 =====
let S=await regen('03 ','03 시스템 구성도 (v3 · Supabase 공용/개인 · PC 는 무상태 워커)',0,1360,2000,1100,'526:303');
label(S,'03 시스템 구성도 (v3)',40,32,{size:28,style:'Bold'});
label(S,'상태는 전부 Supabase 에, PC 는 크롤링·CLIP 추론·스케줄만 하는 "손과 눈". 어느 PC 에서 로그인해도 같은 데이터. service_role 키는 PC 에 두지 않는다.',40,78,{size:14,color:'#555555'});
const pc=box(S,{x:40,y:130,w:780,h:620,fill:GREY[0],stroke:GREY[1],r:14,name:'사용자 PC'});
label(pc,'사용자 PC (윈도우 · 맥 · 여러 대 가능) — 무상태 워커',20,16,{size:17,style:'Bold'});
[['app.auth','이메일 로그인 1회 → 세션 토큰 저장\n이후 anon key + JWT 로만 호출'],['app.worker','batch_locks 획득 → ⓪~⑤ 실행\nAPScheduler · 개인 설정 시각'],['Playwright','1688 목록·상세 (로그인 프로필)\n네이버 통합검색 (캐시 미스만)'],['CLIP · pHash (로컬 추론)','썸네일 20장 임베딩 1~2초\n유사도 매칭 · 동일 이미지 판매자'],['app.admin (로컬 FastAPI)','localhost:8000 · Supabase Auth 로그인\n메뉴 12개 · 호스팅은 2차'],['텔레그램 봇 폴링','worker_leases 임대를 가진 PC 만\n카드 · 콜백 · URL 즉시 분석 입구'],['app.instant','등록 소스 URL → 어댑터 경로 (AI 0회)\n미등록 사이트 → 범용 LLM 추출']].forEach((c,i)=>{const col=i%2,row=Math.floor(i/2);card(pc,{x:20+col*380,y:56+row*104,w:360,h:90,title:c[0],sub:c[1],fill:'#FFFFFF',stroke:GREY[1],tsize:14,ssize:11});});
const pcn=box(pc,{x:20,y:480,w:740,h:118,fill:YEL[0],stroke:YEL[1],r:10,name:'PC 에 남는 것'});
label(pcn,'PC 에 남는 것은 세 가지뿐',14,10,{size:13,style:'Bold',color:'#8A6D00'});
bullets(pcn,14,32,712,['세션 토큰 (~/.auto-store/session.json · 재로그인으로 재생성)','1688 등 로그인이 필요한 소스의 브라우저 프로필 (쿠키가 기기에 묶여 이식 불가 · PC 마다 1회 로그인)','CLIP 모델 파일 (첫 실행 시 자동 다운로드). 그 외 설정·후보·판단·이력·캐시는 전부 Supabase'],{size:11,lh:17,color:'#5A4A00'});
seg(S,820,420,999,420);seg(S,999,470,820,470);
label(S,'anon key + 로그인 JWT · RLS 가 울타리',830,392,{size:12,style:'Bold',color:'#2F855A'});
label(S,'service_role 키는 마이그레이션·시드 전용',830,478,{size:11,color:'#C53030'});
const sb=box(S,{x:1000,y:130,w:960,h:620,fill:GREEN[0],stroke:GREEN[1],r:14,name:'Supabase'});
label(sb,'Supabase 프로젝트 — 상태의 유일한 진실',20,16,{size:17,style:'Bold'});
[['Auth','이메일 로그인 · JWT\nprofiles.role = admin | user'],['Postgres · 공용 스키마 (사실)','사전 · 소스 정의 · source_items · naver_items(캐시)\nimages · matches · market_signals · exchange_rates'],['Postgres · 개인 스키마 (RLS user_id)','user_settings · 시크릿 · 배송 프로필 · 관심 카테고리\ncandidates · rejections · 주문 · api_usage · 잠금'],['pgvector','images.clip vector(512)\n소스 간 그룹핑 · 동일 이미지 전체 검색'],['RPC (security definer)','is_admin() · get/set_my_secret()\n유사도 검색 · 잠금 획득'],['Storage','공개 버킷 product-images\n생성 이미지 → 엑셀 공개 URL'],['Vault','개인 시크릿 (LLM 키 · 봇 토큰)\n처음엔 RLS 컬럼 → 승격']].forEach((c,i)=>{const col=i%2,row=Math.floor(i/2);card(sb,{x:20+col*470,y:56+row*104,w:450,h:90,title:c[0],sub:c[1],fill:'#FFFFFF',stroke:GREEN[1],tsize:14,ssize:11});});
const sbn=box(sb,{x:20,y:480,w:920,h:118,fill:'#FFFFFF',stroke:GREEN[1],r:10,name:'RLS · 잠금'});
label(sbn,'RLS 3종 · 같은 계정 PC 둘',14,10,{size:13,style:'Bold',color:'#2F855A'});
bullets(sbn,14,32,892,['(A) 개인 테이블: user_id = auth.uid() 행만 읽고 쓴다   (B) 공용 참조(사전·요건표·소스 정의): 전원 읽기 · admin 만 쓰기   (C) 공용 수집(상품·카드·매칭·환율): 전원 읽기·추가·갱신 · admin 만 삭제','PC 둘이 같은 계정이면 batch_locks(unique user_id · run_date · kind) 로 한 PC 만 배치, worker_leases(heartbeat) 를 가진 PC 만 텔레그램 폴링. 죽으면 다른 PC 가 인수'],{size:11,lh:17});
seg(S,430,750,430,785,{head:false});seg(S,190,785,1710,785,{head:false});
[['도매 사이트','1688 (로그인 프로필) · 알리 · 타오바오 · 일본 B2B'],['네이버 통합검색','쇼핑 블록 크롤링 → 공용 캐시 (TTL 7일)\n같은 검색어는 두 번 안 함'],['LLM 제공자 (N건만)','OpenAI 기본 / Claude / Gemini\n로고 확인 · 사전 제안 · 콘텐츠 생성'],['환율 API','수출입은행 → 네이버금융 → open.er-api\n공용 exchange_rates 하루 1행'],['텔레그램','1차 · 2차 카드 · 콜백 · URL 입구\n봇 토큰은 개인 시크릿']].forEach((c,i)=>{const x=40+i*380;seg(S,x+150,785,x+150,819);card(S,{x,y:820,w:300,h:84,title:c[0],sub:c[1],fill:'#FFFFFF',stroke:'#A0A0A0',tsize:13,ssize:11});});
const chg=box(S,{x:40,y:930,w:1920,h:140,fill:'#FFFFFF',stroke:'#D0D0D0',r:12,name:'v2 → v3 변경'});
label(chg,'v2 → v3 에서 바뀐 것',20,14,{size:15,style:'Bold'});
bullets(chg,20,42,900,['DB: 집 PC SQLite → Supabase Postgres 하나. 로컬 DB 없음','데이터 소유: 구분 없음 → 공용(사실) / 개인(설정·판단) · RLS 로 계정에 묶임','계정: .env 관리자 1명 → Supabase Auth 로그인 · PC 바꿔도 같은 데이터'],{size:12,lh:19});
bullets(chg,960,42,940,['우선 범위: 수집→등록→주문 전체 → 발굴(①~⑤) 먼저, 등록·주문은 2차','AI: 상품 1건당 LLM 3회 → 발굴 0회/건 (어댑터 · 사전 · CLIP) · N건 로고 확인만','CLIP: 운영 후 개선 → MVP (매칭의 주력) · 비밀값: .env/화면 → Vault, service_role 은 PC 에 없음'],{size:12,lh:19});

// ===== 04 IA (v3 · 메뉴 12개 · 개인 / admin) — 재생성 =====
S=await regen('04 ','04 관리자 정보 구조(IA) · 기능 정의 (v3 · 개인 / admin)',4680,0,2400,1240);
label(S,'04 관리자 정보 구조(IA) · 기능 정의 (v3)',40,32,{size:28,style:'Bold'});
label(S,'로컬 FastAPI 를 각 PC 에서 띄우고 Supabase Auth 로 로그인. 메뉴 12개 중 10개는 개인(내 설정·내 후보), 2개는 admin(공용 사전·소스 정의). 설정의 진실은 DB(user_settings), .env 는 첫 로그인 부트스트랩.',40,78,{size:14,color:'#555555'});
card(S,{x:900,y:130,w:600,h:70,title:'auto-store 관리자 웹 (v3)',sub:'로컬 FastAPI + HTMX · Supabase Auth 로그인 · 어느 PC 에서나 같은 화면 · anon key + JWT',fill:'#1F2933',stroke:null,titleColor:'#FFFFFF',subColor:'#CBD2D9'});
const menus=[['대시보드',0,['오늘 배치 (잠금 보유 PC · 단계 · 건수)','후보 N · 확인 대기 표기 수','오늘 LLM 호출 수 · 추정 비용','차단 · 오류 · 로그인 만료','수동 실행 (수집 / 조회 / 알림)']],['관심 카테고리',0,['소스 선택 → 1688 카테고리 URL','표준 카테고리 (사전이 추천)','추가 한국어 검색 키워드 2~3개\n  → 검색어 품질을 좌우','페이지 수 · 사용 여부','1페이지 테스트','= user_watch_categories (개인)']],['후보 목록',0,['상단 "URL 즉시 분석" 입력창','탭: 오늘 카드 / 후보(미전송) /\n  보류 / 거절 / 승인 진행중','상세: 원가 내역 · 매칭 이미지\n  나열 · 유사도 근거 · 점수 분해','재점수 · 수동 승인 · 거절','즉시 분석 이력 (이전 결과 비교)']],['내 소스',0,['소스 켜기 / 끄기','요청 지연 · 하루 상한 · 차단 허용','배송 프로필 지정','로그인 프로필 저장 (브라우저 열기)\n  PC 마다 1회','헬스 (내 PC 기준)']],['비용 설정',0,['환율 현황 (공용 · 조회만)','배송 프로필 탭\n  요율표 · 현지 배송비 · 대리구매 · 배송일','관세 · 부가세 · 150달러 경계','네이버 · 결제 수수료','마진 기준 · 목표 마진율 · 환차손 완충']],['매칭 설정',0,['가격 방식 (평균 / 중앙값 / 최저)','프리셋 · 정확/유사 임계값','동일 이미지 판매자 cap','하루 카드 N (기본 10)','하루 조회 상한 · LLM 상한','LLM 재판정 on / off']],['제외 규칙',0,['재질 / 품목 / 키워드 탭 (개인)','공용 제외 사유 보기 (읽기)\n  식품 · 화장품 · 브랜드 텍스트','거절 이력 기간 (기본 90일)']],['사전 관리',1,['표준 카테고리 트리 · 검색 키워드','별칭 사전 (zh / ja / ko / en)','속성 코드 · 브랜드 블랙리스트\n  · 스톱워드 · 요건표','확인 대기 큐 승인 / 거절\n  → dict_version +1\n  → 모든 계정에 적용']],['소스 정의',1,['사이트 등록 · 국가 · 통화 · base URL','어댑터 종류 · 셀렉터 · 힌트','1페이지 테스트','공용 정의. 켜고 끄는 건 "내 소스"']],['시스템 설정',0,['AI 제공자 · 모델 · 키 (시크릿)\n  · 연결 테스트','월 예산 · 경고 비율 · 초과 동작','배치 시각 · 요일 · 감시 주기','텔레그램 봇 토큰 · chat_id\n  · 테스트 발송','비밀번호 변경']],['실행 로그',0,['날짜 · 단계 · 소스 · 건수','오류 · 차단 · PC 이름','LLM 호출 수 · 비용']],['주문 관리',0,['(2차) 주문 목록 (상태별)','주문 ↔ 소스 · 옵션 · 원가 · 배대지','체크리스트 통관부호 → … → 완료','예상 도착일 · 실제 원가','월 손익 요약']]];
const MW=176,GAP=16,X0=40;const xc=i=>X0+i*(MW+GAP)+MW/2;
seg(S,1200,200,1200,251);seg(S,xc(0),252,xc(11),252,{head:false});
menus.forEach((m,i)=>{const x=X0+i*(MW+GAP);const ad=m[1]===1;seg(S,xc(i),252,xc(i),299);card(S,{x,y:300,w:MW,h:56,title:m[0],fill:ad?ORANGE[0]:BLUE[0],stroke:ad?ORANGE[1]:BLUE[1],tsize:14});badge(S,x+MW-(ad?58:46),292,ad?'ADMIN':'개인',ad?'#C05621':'#2B6CB0');const b=box(S,{x,y:372,w:MW,h:330,fill:'#FFFFFF',stroke:ad?ORANGE[1]:'#D0D0D0',r:10,name:m[0]+' 기능'});bullets(b,12,12,MW-24,m[2],{size:11,lh:17});});
const extra=[['텔레그램 봇 기능 (v3)',BLUE,['08:00 요약: 소스별 수집 / 차단 · 공용 제외 · 개인 제외 · 후보 · 확인 대기 표기 수 · 오늘 LLM 호출 수와 비용','1차 후보 카드: 이미지 · [1688 · CN] 배지 · 원가(¥·₩) · 마진율 · 제안 판매가 · 경쟁(정확 N · 동일 이미지 판매자 N · 판매처 최대) · 리뷰 최대 · 근거("유사도 0.93 · 500ml 일치")','[승인] [거절] [보류] → 개인 candidates 에 반영 · 거절은 rejections (90일)','2차 미리보기 카드 · [패키지 생성] [수정 요청] [폐기] (2차 범위)','URL 즉시 분석: 등록 소스면 AI 0회로 같은 카드 · 미등록 사이트면 범용 LLM 경로 · /recent','예산 경고 · 배치 미실행 · 소스 차단 · 1688 로그인 만료 ("다시 로그인하세요")','같은 계정 PC 둘이면 worker_leases 임대를 가진 PC 만 폴링 (409 충돌 방지)']],['배치 운영 규칙 (v3)',GREY,['개인 설정 시각(기본 02:00)에 batch_locks 를 먼저 insert 한 PC 가 ⓪~⑤ 실행 · heartbeat 10분 끊기면 다른 PC 가 인수','⓪ 공용 환율은 오늘 행이 없을 때만 갱신 · 사전 dict_version 이 올랐으면 비용 없이 재정규화','③ 네이버 조회는 공용 naver_queries 캐시(7일) 먼저 · 다른 계정이 이미 본 검색어는 요청 0','하루 건수 세 가지: 수집 규모(카테고리별 페이지 수) / 분석 상한(네이버 조회 · LLM 호출) / 카드 N(기본 10)','AI 는 ⑤ 카드 N건 로고 확인 + ② 미등록 표기 제안(묶어서 1회) 만 · 요약에 호출 수 표시','알림 시각(기본 08:00) ⑤ 점수 상위 N건 · 로고 감지되면 다음 순위 승격 (최대 2N 확인)','⑩ 감시(2차)는 내 listings 대상이되 재수집 가격은 공용 source_items 에도 반영']],['설정값의 출처 · 로그인 (v3)',GREEN,['python -m app.auth login → 이메일 · 비밀번호 → access/refresh 토큰을 PC 에 저장 · 만료 시 자동 refresh','첫 로그인 때 user_settings 가 없으면 .env 기본값으로 1행 생성 · 이후 화면(DB) 값이 유일한 진실','PC 를 바꿔도 같은 값 · .env 는 Supabase URL · anon key · 부트스트랩 기본값만','개인 시크릿(LLM 키 · 봇 토큰 · 수출입은행 키)은 Vault 또는 RLS 보호 컬럼 · get/set_my_secret RPC','service_role 키는 supabase/migrations · seed 스크립트에서만 · 그 PC 에서도 작업 후 지운다','공용 사전은 admin 만 수정 · 공용 수집 데이터는 created_by 기록 · admin 삭제 가능','role 은 profiles.role · 첫 계정은 시드로 admin · 계정이 늘어도 되는 구조']]];
extra.forEach((e,i)=>{const x=40+i*780;const b=box(S,{x,y:760,w:750,h:440,fill:e[1][0],stroke:e[1][1],r:12,name:e[0]});label(b,e[0],20,16,{size:17,style:'Bold'});bullets(b,20,52,710,e[2],{size:13,lh:22});});

// ===== 09 운영 범위 (v3 · 1차 발굴 / 2차 등록·주문 / 개선) — 재생성 =====
S=await regen('09 ','09 운영 범위 · 1차 발굴 → 2차 등록·주문·감시 (v3)',8800,1360,1900,1000);
label(S,'09 운영 범위 · 1차 발굴 → 2차 등록·주문·감시 (v3)',40,32,{size:28,style:'Bold'});
label(S,'돌아가는 시스템이 먼저. v3 에서는 발굴(①~⑤)이 끝까지 돌아가 매일 아침 후보 카드를 받는 것이 1차 목표. 각 단계 끝에 실제 1688 카테고리 1개로 끝까지 돌려본다. (2026-11-01)',40,78,{size:14,color:'#555555'});
const p1=box(S,{x:40,y:120,w:760,h:840,fill:'#F0FFF4',stroke:GREEN[1],r:12,name:'1차 발굴'});
label(p1,'1차 · 아이템 발굴 (①~⑤)',20,16,{size:18,style:'Bold',color:GREEN[1]});
[['계정·데이터','Supabase Auth 로그인 · 공용/개인 스키마 · RLS · 시드(사전 5종 · 요건표 · 네이버 카테고리) · 개인 설정 화면'],['소싱','1688 내장 어댑터(목록·상세 · 로그인 프로필) · 관심 카테고리(URL + 표준 카테고리 + 한국어 키워드 + 페이지 수) · 요청 정책 · 차단 감지'],['정규화','사전 기반(재질 · 품목 · 카테고리 · 브랜드 텍스트 · 스톱워드 · 숫자/단위) · 공용 제외 · 미등록 표기 확인 큐(LLM 제안은 하루 상한)'],['국내 조회','네이버 크롤링 + 공용 캐시(TTL) · 썸네일 pHash · CLIP 임베딩 · CLIP·규칙 매칭(정확/유사) · 동일 이미지 판매자 수 · 시장 신호'],['상품성 판단','개인 원가·마진율(대리구매 · 환차손) · 후보 점수(마진 + 경쟁 + 수요 대리값 − 리스크) · 요건 3단계 · 150달러 · 거절 이력 · 하루 N'],['알림','텔레그램 1차 카드(이미지 · 원가 · 마진 · 경쟁 · 리뷰 · 근거) · N건 로고 비전 · [승인][거절][보류] · 스케줄 · 잠금 · 미실행 경고'],['즉시 분석','URL 1건(텔레그램 · 웹 · CLI) · 등록 소스는 어댑터 경로(AI 0회) · 미등록은 범용 LLM · 이력은 개인 analysis_requests'],['관리자 웹','로그인 · 대시보드 · 관심 카테고리 · 후보 목록 · 사전·확인 큐(admin) · 비용 · 매칭 · 시스템 설정']].forEach((r,i)=>{const y=52+i*96;const t=box(p1,{x:20,y,w:130,h:80,fill:'#FFFFFF',stroke:GREEN[1],r:8,name:r[0]});label(t,r[0],0,30,{size:13,style:'Bold',color:GREEN[1],w:130,align:'CENTER'});label(p1,r[1],170,y+6,{size:12,color:'#1F1F1F',w:570,lh:19});});
const p2=box(S,{x:820,y:120,w:560,h:840,fill:'#FFF7E0',stroke:'#B7791F',r:12,name:'2차 등록·주문·감시'});
label(p2,'2차 · 등록 · 주문 · 감시 (⑥~⑩)',20,16,{size:18,style:'Bold',color:'#8A6D00'});
label(p2,'발굴이 돌아간 뒤. v2 설계 그대로, 개인 테이블에 저장',20,44,{size:12,color:'#8A6D00'});
[['등록','상세 수집 · 키워드 상품명 · 네이버 카테고리 추천 · 옵션 정리 · 고지·배송·반품 블록 · 이미지 모드 A + 템플릿 · 2차 카드 · Supabase Storage · 엑셀'],['주문·배송','주문 처리 화면 · 개인통관고유부호 체크리스트 · 예상 도착일'],['재고·가격','등록 상품 소스 감시(⑩) · 재수집 가격은 공용에도 반영'],['정산','주문별 실제 원가 · 월 손익 요약'],['소싱 확장','알리익스프레스 내장 어댑터 · 범용 CSS 어댑터']].forEach((r,i)=>{const y=76+i*150;const t=box(p2,{x:20,y,w:110,h:70,fill:'#FFFFFF',stroke:'#B7791F',r:8,name:r[0]});label(t,r[0],0,26,{size:13,style:'Bold',color:'#8A6D00',w:110,align:'CENTER'});label(p2,r[1],150,y+4,{size:12,color:'#1F1F1F',w:390,lh:19});});
const p3=box(S,{x:1400,y:120,w:480,h:840,fill:'#F7F7F5',stroke:'#A0A0A0',r:12,name:'운영 후 개선'});
label(p3,'운영 후 개선',20,16,{size:18,style:'Bold',color:'#555555'});
[['소싱','타오바오 · 일본 B2B · LLM 추출 어댑터 · 소스 간 그룹핑(pgvector 쿼리 한 줄)','1688 로 월 매출이 나면'],['역방향 발굴','공용 네이버 캐시에서 "리뷰 많고 판매처 적은 상품" → 1688 에서 찾기','캐시가 쌓이면'],['상품성','정확도 프리셋 세분화 · 데이터랩 수요 신호(추이 ±10 으로 교체)','오판 사례가 쌓이면'],['등록','이미지 모드 B / C · 커머스 API 자동 등록','잘 팔리는 상품이 생기면'],['재고·가격','환율 급변 전체 재계산 · 국내 경쟁가 추적',''],['시스템','관리자 웹 호스팅(웹훅) · CS 자동 안내 · 회계 연동 · Vault 승격','계정이 늘기 전에']].forEach((r,i)=>{const y=52+i*128;label(p3,r[0],20,y,{size:14,style:'Bold',color:'#555555'});label(p3,r[1],20,y+24,{size:12,color:'#333333',w:440,lh:19});if(r[2])label(p3,'넣을 때: '+r[2],20,y+74,{size:11,color:'#8A8A8A',w:440});});

// ===== 10 데이터 모델 · 공용 vs 개인 (v3) — 신규 =====
S=section('10 데이터 모델 · 공용 vs 개인 · RLS (v3)',10760,1360,2100,1000);
label(S,'10 데이터 모델 · 공용 vs 개인 · RLS (v3)',40,32,{size:28,style:'Bold'});
label(S,'경계 기준: "내 배대지 요율을 바꾸면 값이 달라지는가?" — 달라지면 개인, 아니면 공용. 공용은 user_id 없이 created_by 만, 개인은 user_id = auth.uid() 로 RLS. 모든 테이블은 Supabase Postgres.',40,78,{size:14,color:'#555555'});
const cols=[['공용 참조 데이터','admin 만 쓰기 · 시드로 시작 · dict_version 으로 재정규화','#FFF7E0','#B7791F',['sources — 소스 정의 (adapter_key · base_url · 셀렉터)','source_categories — 1688 URL ↔ 표준 카테고리','canonical_categories — 트리 · naver_cat_id · item_type · search_keywords_ko[]','category_aliases — 표기(zh/ja/ko/en) → 표준','attribute_aliases — 不锈钢 → stainless','brand_blacklist — 브랜드 · 캐릭터명','title_stopwords — 跨境 · 爆款 · 批发 …','requirements — item_type → pass/required/excluded','naver_categories — cat_id → 경로명','mapping_queue — 미등록 표기 · LLM 제안 · 승인 대기','dict_meta — dict_version']],['공용 수집 데이터','로그인 사용자(워커) 누구나 추가·갱신 · admin 삭제 · created_by 기록','#DDEBFF','#2B6CB0',['source_items — 1688 상품 (가격 구간 · MOQ · 이미지 · 속성 원문)','source_items_normalized — 사전 결과 · search_queries[] · excluded_reason · mapping_pending','images — kind · phash · clip vector(512)','naver_queries — 검색어 → nv_mids[] · fetched_at (TTL 7일 캐시 키)','naver_items — nv_mid · 가격 · 리뷰 · 찜 · 판매처 · cat_id · 썸네일','matches — source_item ↔ nv_mid · exact/similar · method(clip/rule/llm) · similarity','market_signals — 정확/유사 수 · 동일 이미지 판매자 · 리뷰 · 가격 평균/중앙값/최저','source_item_details — 옵션 · 상세 이미지 · 무게 (⑥)','exchange_rates — 통화 · rate_krw · 하루 1행']],['개인 데이터 (RLS user_id)','내 행만 보인다 · PC 를 바꿔도 같은 값','#D9F2E3','#2F855A',['profiles — role(admin/user) · telegram_chat_id','user_settings — 비용 · 매칭 · 건수 세 가지 · 스케줄 · 예산 · AI','user_secrets / Vault — LLM 키 · 봇 토큰 · 수출입은행 키','shipping_profiles — 요율표 · 현지 배송비 · 대리구매 · lead_days','user_sources · user_watch_categories · user_exclusion_rules','candidates — 원가 내역 · 마진 · 점수 · status · 결정 (상태 머신)','rejections — source_item · phash · 90일','analysis_requests — 즉시 분석 이력','generated_contents · packages · listings · monitor_events · orders · order_costs (2차)','api_usage — 예산 집계 · run_logs — PC 이름 · 단계 · 건수','batch_locks · worker_leases — PC 둘 조정']]];
cols.forEach((c,i)=>{const x=40+i*680,w=i===2?700:640;const b=box(S,{x,y:130,w,h:520,fill:c[2],stroke:c[3],r:12,name:c[0]});label(b,c[0],20,16,{size:18,style:'Bold'});label(b,c[1],20,44,{size:12,color:'#555555',w:w-40});bullets(b,20,74,w-40,c[4],{size:12,lh:20});});
const pol=[['(A) 개인 테이블 — 내 행만','create policy own_rows on candidates for all to authenticated\n  using (user_id = auth.uid()) with check (user_id = auth.uid());','#D9F2E3','#2F855A'],['(B) 공용 참조 — 전원 읽기 · admin 쓰기','create policy read_all on category_aliases for select to authenticated using (true);\ncreate policy admin_rw on category_aliases for all to authenticated\n  using (is_admin()) with check (is_admin());','#FFF7E0','#B7791F'],['(C) 공용 수집 — 전원 읽기·추가·갱신 · admin 삭제','read_all (select) · worker_insert (insert, created_by = auth.uid())\nworker_update (update) · admin_delete (delete, is_admin())','#DDEBFF','#2B6CB0']];
pol.forEach((p,i)=>{const x=40+i*680,w=i===2?700:640;const b=box(S,{x,y:670,w,h:150,fill:'#FFFFFF',stroke:p[3],r:10,name:p[0]});label(b,p[0],16,12,{size:14,style:'Bold',color:p[3]});label(b,p[1],16,40,{size:11,color:'#333333',w:w-32,lh:17});});
label(S,'is_admin() 은 profiles.role = \'admin\' 을 보는 security definer 함수 · 개인 시크릿은 get_my_secret(name) / set_my_secret(name, value) RPC 로만 (auth.uid() 검사)',40,830,{size:12,color:'#555555',w:2020});
const sm=box(S,{x:40,y:860,w:2020,h:110,fill:YEL[0],stroke:YEL[1],r:10,name:'상태 표현'});
label(sm,'상태 표현 (v2 상태 머신과의 대응)',14,10,{size:13,style:'Bold',color:'#8A6D00'});
label(sm,'v2 의 collected → normalized → filtered_out → matched 는 공용 테이블의 존재와 컬럼으로 표현: source_items(수집) → source_items_normalized(excluded_reason 있으면 공용 제외 · mapping_pending 이면 확인 대기) → market_signals(조회됨).\n개인 candidates.status: candidate → held / rejected_1 → approved_1 → detail_collected → content_generated → rejected_2 / revise → approved_2 → packaged → listed → suspended. 마진 미달은 below_margin 으로 남겨 "후보(미전송)" 조회에 쓴다.',14,32,{size:11,color:'#5A4A00',w:1990,lh:17});

// ===== 11 발굴 배치 ⓪~⑤ · AI 최소화 (v3) — 신규 =====
S=section('11 발굴 배치 ⓪~⑤ · AI 0회/건 (v3)',12920,1360,2300,1000);
label(S,'11 발굴 배치 ⓪~⑤ · AI 0회/건 (v3)',40,32,{size:28,style:'Bold'});
label(S,'새벽(개인 설정 시각) 배치 잠금을 얻은 PC 한 대가 실행. 추출은 어댑터, 정규화는 사전, 매칭은 CLIP·pHash·규칙. LLM 은 ⑤ 에서 카드로 나갈 N건의 로고 확인에만. 하루 200건 기준 LLM 10~30회 (v2 설계 600회).',40,78,{size:14,color:'#555555'});
const steps=[['⓪ 준비','공용 환율 갱신 (오늘 행 없을 때만)\n사전 dict_version 확인\n내 설정 로드','AI 0회',GREY,'→ 공용 exchange_rates'],['① 소스별 수집','내 관심 카테고리 × 1688 어댑터\n목록 카드에서 제목 · 가격 구간 · MOQ · 이미지\n이미 있으면 가격 · last_seen 만 갱신','AI 0회',GREEN,'→ 공용 source_items'],['② 사전 정규화','스톱워드 제거 · 숫자/단위 추출\n재질 · 품목 · 카테고리 사전 · 브랜드 텍스트\n공용 제외 · 미등록 표기 → 확인 큐','AI 0회 (제안만 상한 내 1회)',GREEN,'→ 공용 source_items_normalized'],['③ 국내 조회','naver_queries 캐시(7일) → 크롤링\n썸네일 pHash · CLIP → images\nCLIP 유사도 + 숫자 일치 → exact / similar','AI 0회',GREEN,'→ 공용 naver_items · matches · market_signals'],['④ 개인 원가 · 점수','공용 환율 × 내 배송 프로필 · 수수료율\n내 가격 방식 · 내 제외 규칙 · 거절 이력\n마진율 · 제안 판매가 · 점수','AI 0회',GREEN,'→ 개인 candidates'],['⑤ 1차 알림','점수 상위 N건 선정\nN건만 비전 LLM 로고 확인 → 감지 시 승격\n텔레그램 카드 [승인][거절][보류]','LLM: N건 로고 (하루 ≈ N회)',ORANGE,'→ 개인 candidates.status · 텔레그램']];
steps.forEach((s,i)=>{const x=40+i*370;card(S,{x,y:160,w:330,h:150,title:s[0],sub:s[1],fill:'#FFFFFF',stroke:s[3][1],tsize:15,ssize:11});badge(S,x+12,148,s[2],s[3][1]);label(S,s[4],x,318,{size:11,style:'Medium',color:s[3][1],w:330});if(i<5)seg(S,x+330,235,x+369,235);});
const ai=box(S,{x:40,y:370,w:1100,h:270,fill:ORANGE[0],stroke:ORANGE[1],r:12,name:'AI 가 쓰이는 지점'});
label(ai,'AI 가 쓰이는 지점 — 전체 목록 (이 밖에는 없다)',20,16,{size:16,style:'Bold',color:'#7B341E'});
bullets(ai,20,48,1060,['⑤ 카드로 나갈 N건의 대표 이미지 로고 확인 (비전 · 하루 ≈ N회) — 감지되면 rejected_1(brand) + rejections, 다음 순위 승격 (최대 2N)','② 사전 미등록 표기의 표준 카테고리 · 코드 제안 — 하루 상한 안에서 미등록 20개를 한 호출에 묶어 1회. 사전이 차면 0 에 수렴','⑦ 승인된 상품의 한국어 상품명 · 설명 · 옵션 정리 (2차 · 승인 건수만큼 · 월 예산 적용)','즉시 분석에서 미등록 사이트 URL 의 범용 추출 (등록 소스는 어댑터 경로라 0회) — 지금 돌아가는 v2 CLI 가 이 경로','선택: N건의 매칭 LLM 재판정 (개인 설정 llm_rejudge_top_n · 기본 off)'],{size:12,lh:21,color:'#3D2317'});
const sc=box(S,{x:1180,y:370,w:1080,h:270,fill:'#FFFFFF',stroke:'#4A5568',r:12,name:'후보 점수 (④)'});
label(sc,'후보 점수 (④ · 가중치는 개인 매칭 설정)',20,16,{size:16,style:'Bold'});
label(sc,'점수 = 마진율×100\n     + 경쟁: 정확 0~2건 +15 · 3~5건 +5 · 6건 이상 0 · 동일 이미지 판매자 ≥ cap −20 · 가격비교 판매처 ≥ 100곳 −10\n     + 수요 대리값: 매칭 리뷰 최대 ≥ 1,000 +10 · 100~999 +5 · 찜 ≥ 500 +5   (데이터랩 붙으면 추이 ±10 으로 교체)\n     − 리스크: 무게 미확인 −5 · 150달러 경계 −5 · 요건 필요 −10 · 요건 미확정 −10\n\n국내비교가 = market_signals 의 price_mean | median | min 중 내 설정 · 마진율 = (국내비교가 − 총원가) / 국내비교가\n제안 판매가 = (총원가 − 수수료) ÷ (1 − 목표마진율 − 수수료율), 100원 올림',20,46,{size:12,color:'#333333',w:1040,lh:20});
const cnt=box(S,{x:40,y:660,w:1100,h:150,fill:BLUE[0],stroke:BLUE[1],r:12,name:'하루 건수 세 가지'});
label(cnt,'"하루 몇 개" 는 세 가지로 나뉜다 (전부 개인 설정)',20,16,{size:16,style:'Bold',color:'#1A365D'});
bullets(cnt,20,48,1060,['수집 규모 — 관심 카테고리별 max_pages · 소스별 daily_cap (요청 수)','분석 상한 — daily_lookup_cap (네이버 조회) · daily_llm_cap (LLM 호출) · instant_daily_limit (즉시 분석)','카드 건수 N — 마진율 ≥ 기준 중 점수 상위 몇 건을 카드로 보낼지 (기본 10). 나머지는 "후보(미전송)"'],{size:12,lh:21,color:'#1A365D'});
const cost=box(S,{x:1180,y:660,w:1080,h:150,fill:'#FFFFFF',stroke:'#D0D0D0',r:12,name:'비용 비교'});
label(cost,'비용 · 요청 수 비교 (하루 200건 기준)',20,16,{size:16,style:'Bold'});
bullets(cost,20,48,1040,['v2 설계: 상품마다 LLM 3회(추출 25원 · 정규화 16원 · 매칭 26원 ≈ 67원) → 600회/일 ≈ 13,000원/일 · 네이버 600요청/일 (차단 위험)','v3: 발굴 0회/건 + ⑤ N건 로고 + ② 제안 1회 → 10~30회/일 (수백 원) · 네이버는 캐시 미스만 · 다른 계정이 본 검색어는 0','진짜 공사는 AI 대체가 아니라 1688 어댑터 (로그인 프로필 · 목록 구조 · 차단 감지)'],{size:12,lh:21});
const inst=box(S,{x:40,y:830,w:2220,h:130,fill:YEL[0],stroke:YEL[1],r:10,name:'즉시 분석 입구'});
label(inst,'별도 입구 · URL 즉시 분석 (텔레그램 · 관리자 웹 · CLI)',14,10,{size:13,style:'Bold',color:'#8A6D00'});
label(inst,'URL → 공용 sources.base_url 로 소스 판별 → 등록 소스면 어댑터 detail → ② → ③ → ④ → 카드 (AI 0회, 결과는 공용 캐시에 적재) / 미등록 사이트면 범용 스냅샷 → LLM 추출 · 정규화 → ③ → ④ → 카드 (v2 CLI 경로, LLM 2~3회).\n이력은 개인 analysis_requests · 같은 URL 재요청 시 이전 결과와 나란히 · 하루 상한은 개인 설정. 승인하면 일반 후보와 같이 ⑥⑦ 로 이어진다.',14,32,{size:11,color:'#5A4A00',w:2190,lh:17});

// ===== 01 프로세스 — 문구 갱신 + v3 띠 =====
const s1=findSec('01 ')||await getNode('526:2');
if(s1){
  retext(s1,{'① 소스별 수집':'① 소스별 수집 (어댑터 · AI 0회)','등록 소스 × 카테고리\n어댑터가 원시 데이터 반환':'내 관심 카테고리 × 1688 어댑터\n→ 공용 source_items','② 정규화 · 필터':'② 사전 정규화 (AI 0회)','통화·언어·카테고리 별칭\n브랜드 로고 감지 · 제외 규칙':'스톱워드 · 숫자/단위 · 재질/품목 사전\n브랜드 텍스트 · 공용 제외 · 확인 큐','AI (선택: Claude / Gemini / OpenAI)':'AI (N건 로고 확인 · 사전 제안만)','언어 무관 정규화 · 로고 감지\n카테고리 제안 → 확인 큐':'사전 미등록 표기 제안 (하루 상한)\n카드 N건 로고 비전 확인','네이버 상위 N개 · 정확/유사\n경쟁 강도 · 수요 · 카테고리 추천':'공용 캐시 → 크롤링 → CLIP·pHash 매칭\n정확/유사 · 동일 이미지 판매자 · 리뷰','총원가 · 마진율 · 후보 점수\n품목 요건 · 150달러 경계':'내 설정으로 원가 · 마진율 · 점수\n→ 개인 candidates','후보 점수순 상위 N건 (기본 10)\n경쟁 · 수요 · 리뷰 · 근거 표시':'상위 N건 로고 비전 확인 → 카드\n경쟁 · 리뷰 · 유사도 근거 · LLM 비용','v2 멀티 소스 · 하루 1회 새벽 배치 → 아침 텔레그램 후보 수신 → 2단계 승인 → 등록 패키지(엑셀) 산출':'v3 · Supabase 공용/개인 데이터 · 발굴 단계 AI 0회/건 · 하루 1회 새벽 배치 → 아침 텔레그램 후보 → 2단계 승인 → 등록 패키지(엑셀)','소스·카테고리 매핑·제외 규칙·비용':'관심 카테고리 · 사전 · 내 설정 (Supabase)','자동 수집만: 수출입은행 API\n→ 네이버 금융 크롤링 → 마지막값':'공용 exchange_rates · 하루 1회\n수출입은행 → 네이버금융 → er-api','Supabase Storage + output/':'Supabase Storage · 개인 packages','소스별 로그인 프로필':'소스별 로그인 프로필 (PC 마다 1회)'});
  const h1=holderOf(s1);const H=s1.height;s1.resizeWithoutConstraints(s1.width,H+100);if(h1!==s1)h1.resize(h1.width,H+100);
  const band=box(h1,{x:120,y:H+12,w:Math.max(800,s1.width-240),h:76,fill:GREEN[0],stroke:GREEN[1],r:10,name:'v3 변경 띠'});
  label(band,'v3 (2026-11-01) · Supabase 단일 DB · 공용/개인 데이터 · 계정 로그인 · 발굴 우선 · AI 0회/건',16,10,{size:14,style:'Bold',color:'#22543D'});
  label(band,'①~⑤ 는 보드 11(발굴 배치) · 데이터는 보드 10(공용 vs 개인) · 구성은 보드 03. 로컬 DB 는 없다 — 상태는 전부 Supabase, PC 는 크롤링·CLIP·스케줄만. 같은 계정의 PC 둘이면 batch_locks 로 한 PC 만 실행. LLM 은 카드로 나갈 N건의 로고 확인과 사전 미등록 표기 제안에만 쓰고, 승인 뒤 ⑦ 콘텐츠 생성에서 다시 쓴다.',16,36,{size:12,color:'#22543D',w:Math.max(760,s1.width-280)});
}

// ===== 02 상태 머신 — v3 메모 =====
const s2=findSec('02 ')||await getNode('526:191');
if(s2){
  const h2=holderOf(s2);const need=1010;if(s2.height<need){s2.resizeWithoutConstraints(s2.width,need);if(h2!==s2)h2.resize(h2.width,need);}
  const nb=box(h2,{x:120,y:870,w:1000,h:120,fill:GREEN[0],stroke:GREEN[1],r:10,name:'v3 상태 표현'});
  label(nb,'v3 상태 표현',20,12,{size:14,style:'Bold',color:'#22543D'});
  label(nb,'collected · normalized · filtered_out · mapping_pending · matched 는 더 이상 한 상품의 status 가 아니라 공용 테이블의 존재와 컬럼이다 (source_items → source_items_normalized.excluded_reason / mapping_pending → market_signals). 개인 candidates.status 가 candidate 부터 listed · suspended 까지의 체인을 가진다. below_margin 은 "후보(미전송)" 조회용. 거절은 rejections(90일) 로 모든 소스에서 재등장을 막는다.',20,36,{size:12,color:'#22543D',w:960,lh:18});
}

// ===== 06 텔레그램 카드 — 문구 갱신 =====
const s6=findSec('06 ');
if(s6){retext(s6,{'1688가  ¥18.5 × 최소 2개 = 6,900원\n국내 비교가  24,900원 (상위 10개 평균)\n총원가  13,400원  →  마진율 46%\n경쟁  정확 3 · 동일 이미지 판매자 2곳 · 결과 1,240건\n수요  최근 3개월 +12% ↑ · 리뷰 평균 48 (최대 210)\n근거  용량 500ml · 스테인리스 · 형태 일치 (0.91)\n점수  71 · 요건 통과 · 재질 스테인리스':'1688가  ¥18.5 × 최소 2개 = 6,900원\n국내 비교가  24,900원 (정확 · 평균 · 공용 캐시)\n총원가  13,400원  →  마진율 46% · 제안 21,900원\n경쟁  정확 3 · 동일 이미지 판매자 2곳 · 판매처 최대 41곳\n리뷰  최대 210 · 찜 85  (수요 대리값 +5)\n근거  이미지 유사도 0.93 · 용량 500ml 일치 (CLIP · 규칙)\n점수  71 · 요건 통과 · 로고 확인 통과 (비전 1회)','총원가 9,800원 → 마진율 38% · 정확 1 · 동일 이미지 0곳\n수요 +4% · 리뷰 평균 12 · 점수 64 · 요건 통과':'총원가 9,800원 → 마진율 38% · 정확 1 · 동일 이미지 0곳\n유사도 0.88 · 리뷰 최대 12 · 점수 64 · 요건 통과'});}

const summary={removed,created:ids.length,retexted:changed.length};
console.log('06 완료',summary);
figma.notify('06 완료: 03·04·09 재생성, 10·11 신규, 01·02·06 갱신 · 이제 05 를 다시 실행하세요');
