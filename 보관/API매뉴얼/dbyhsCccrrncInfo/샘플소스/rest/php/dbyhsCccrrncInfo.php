<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>병해충 발생정보</title>
<script type='text/javascript'>

//검색
function fncSearch(){
	with(document.searchApiForm){
		method="get";
		action = "dbyhsCccrrncInfo.php";
		target = "_self";
		submit();
	}
}

//페이지 이동
function fncGoPage(page){
	with(document.searchApiForm){
		pageNo.value = page;
		method="get";
		action = "dbyhsCccrrncInfo.php";
		target = "_self";
		submit();
	}
}

</script>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>병해충 발생정보</strong></h3>
<hr>

<form name="searchApiForm">
<input type="hidden" name="pageNo">
<select name="sYear"> 
<?PHP
//병해충 발생정보 연도 콤보
if(true){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "dbyhsCccrrncInfo";
	//오퍼레이션 명
	$operationName = "dbyhsCccrrncInfoYear";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;

	$url = "http://api.nongsaro.go.kr/service" . $parameter; 

	//XML Parsing
	$xml = file_get_contents($url);
	//PHP5.x 이상이 설치되어 있어야 하며, php.ini에 allow_url_fopen을 on으로 해주시기 바랍니다.
	$object = simplexml_load_string($xml);

	foreach($object->body[0]->items[0]->item as $item){
		//년도 카운트
		$yearCnt = $item->yearCnt;
		//년도 명
		$yearCode = $item->yearCode;
?>
		<option value="<?=$yearCode?>" <?PHP if(isset($_REQUEST["sYear"])){ if($_REQUEST["sYear"]==$yearCode) echo "selected"; }?>><?=$yearCode?>(<?=$yearCnt?>)</option>
<?PHP
	}
}
?>
</select>
<select name="sType"> 
	<option value="sCntntsSj" <?PHP if(isset($_REQUEST["sType"])){ if($_REQUEST["sType"]=="sCntntsSj") echo "selected"; }?>>제목</option>
	<option value="sWriteNm" <?PHP if(isset($_REQUEST["sType"])){ if($_REQUEST["sType"]=="sWriteNm") echo "selected"; }?>>작성자</option>
</select>
<input type="Text" name="sText" value="<?PHP if(isset($_REQUEST["sText"])){ echo $_REQUEST["sText"]; }?>">
<input type="button" name="search" value="검색" onclick="return fncSearch();"/>
</form>

<form name="pageApiForm">
<input type="hidden" name="pageNo">
</form>

<?PHP
//병해충 발생정보 리스트
if(true){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "dbyhsCccrrncInfo";
	//오퍼레이션 명
	$operationName = "dbyhsCccrrncInfoList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;
	
	//년도 검색
	if(isset($_REQUEST["sYear"])){
		if($_REQUEST["sYear"]=="전체"){
			$parameter .= "&sYear=";
		}else{
			$parameter .= "&sYear=".$_REQUEST["sYear"];
		}
	}
	//검색 조건
	if(isset($_REQUEST["sType"])){
		$parameter .= "&sType=";
		$parameter .= $_REQUEST["sType"];
	}
	//검색어
	if(isset($_REQUEST["sText"])){
		$parameter .= "&sText=";
		$parameter .= $_REQUEST["sText"];
	}
	//페이지 이동
	if(isset($_REQUEST["pageNo"])){
		$parameter .= "&pageNo=";
		$parameter .= $_REQUEST["pageNo"];
	}

	$url = "http://api.nongsaro.go.kr/service" . $parameter; 

	//XML Parsing
	$xml = file_get_contents($url);
	$object = simplexml_load_string($xml);

	if(count($object->body[0]->items[0]->item) == 0){
?>
	<h3>조회한 정보가 없습니다.</h3>
<?PHP
	}else{
?>
	<hr>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<colgroup>
			<col width="50%"/>
			<col width="10%"/>
			<col width="15%"/>
			<col width="10%"/>
			<col width="15%"/>
		</colgroup>
		<tr>
			<th>제목</th>
			<th>작성자</th>
			<th>등록일</th>
			<th>조회수</th>
			<th>첨부</th>
		</tr>
<?PHP
		foreach($object->body[0]->items[0]->item as $item){
			//컨텐츠 제목
			$cntntsSj = $item->cntntsSj;
			//등록자
			$updusrEsntlNm = $item->updusrEsntlNm;
			//등록 일자
			$registDt = $item->registDt;
			//조회수
			$cntntsRdcnt = $item->cntntsRdcnt;
			//파일 경로
			$downFile = $item->downFile;
			//파일 명
			$rtnOrginlFileNm = $item->rtnOrginlFileNm;
			//컨텐츠 번호
			$cntntsNo = $item->cntntsNo;
?>
		<tr>
			<td><?=$cntntsSj?></td>
			<td align="center"><?=$updusrEsntlNm?></td>
			<td align="center"><?=$registDt?></td>
			<td align="center"><?=$cntntsRdcnt?></td>
			<td align="center"><a href="<?=$downFile?>">파일 다운로드</a></td>
		</tr>
<?PHP
		}
?>
	</table>
<?PHP
	}
//페이징 처리
	//한 페이지에 제공할 건수
	$numOfRows = $object->body[0]->items[0]->numOfRows;
	//조회된 총 건수
	$totalCount = $object->body[0]->items[0]->totalCount;
	//조회할 페이지 번호
	$pageNo = $object->body[0]->items[0]->pageNo;
	
	$pageGroupSize = 10;
	$pageSize = 0;

	$pageSize = (int)$numOfRows;
	if($pageSize==0) $pageSize=10;
	
	$start = (int)$pageNo; 
	if($start==0)$start=1;

	$currentPage = (int)$pageNo;
	
	$startRow = ($currentPage -1) * $pageSize +1;//한 페이지의 시작글 번호 
	$endRow = $currentPage * $pageSize;//한 페이지의 마지막 글번호         

	$count = (int)$totalCount;
	$number=0;

	$number=$count-($currentPage-1)*$pageSize;//글목록에 표시할 글번호                                                                  
		
	//페이지그룹의 갯수                                                                                                             
	//ex) pageGroupSize가 3일 경우 '[1][2][3]'가 pageGroupCount 개 만큼 있다.                                                       
	$pageGroupCount = $count/($pageSize*$pageGroupSize);

	//페이지 그룹 번호                                                                                                              
	//ex) pageGroupSize가 3일 경우  '[1][2][3]'의 페이지그룹번호는 1 이고  '[2][3][4]'의 페이지그룹번호는 2 이다.                   
	$numPageGroup = (int)ceil((double)$currentPage/$pageGroupSize);

	if($count > 0){
		$pageCount = $count / $pageSize + ( $count % $pageSize == 0 ? 0 : 1);
		$startPage = $pageGroupSize*($numPageGroup-1)+1;
		$endPage = $startPage + $pageGroupSize-1;
		$startPnt = 0;

		if($endPage > $pageCount){
			$endPage = $pageCount;
		}		

		if($numPageGroup > 1){
			$startPnt = ($numPageGroup-2)*$pageGroupSize+1;
			echo "<a href='javascript:fncGoPage(".$startPnt.");'>[이전]</a>";
		}

		for($i=$startPage; $i<=$endPage; $i++){
			$startPnt = $i;
			echo "<a href='javascript:fncGoPage(".$startPnt.");'>";

			if($currentPage == $i){
				echo "<strong>[$i]</strong>";
			}else{
				echo "[$i]";
			}
			echo "</a>";
		}

		if($numPageGroup < $pageGroupCount){
			$startPnt = ($numPageGroup*$pageGroupSize+1);
			echo "<a href='javascript:fncGoPage(".$startPnt.");'>[다음]</a>";
		}
	}
//페이징 처리 끝
}
?>
</body>
</html>