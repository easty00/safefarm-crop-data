<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>농작업 일정</title>
<script type='text/javascript'>
//세부항목 리스트 이동
function fncNextList(kCode, cNm){
	with(document.listApiForm){
		listCategoryCode.value = kCode;
		listCategoryNm.value = cNm;
		method="get";
		action = "farmWorkingPlan.php";
		target = "_self";
		submit();
	}
}
function move(dNo,nm){
	with(document.listApiForm){
		cntntsNo.value = dNo;
		sj.value = nm;
		method="get";
		action = "farmWorkingPlan_D.php";
		target = "_self";
		submit();
	}
}
</script>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>농작업 일정</strong></h3><hr>
<form name="listApiForm">
	<input type="hidden" name="listCategoryCode" value="<?=$_REQUEST["listCategoryCode"]?>>">
	<input type="hidden" name="listCategoryNm" value="<?=$_REQUEST["listCategoryNm"]?>">
	<input type="hidden" name="cntntsNo" >
	<input type="hidden" name="sj" >
</form>

<?PHP
//일정 리스트
if(true){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "farmWorkingPlanNew";
	//오퍼레이션 명
	$operationName = "workScheduleGrpList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;

	$url = "http://api.nongsaro.go.kr/service" . $parameter;

	//XML Parsing
	$xml = file_get_contents($url);
	//PHP5.x 이상이 설치되어 있어야 하며, php.ini에 allow_url_fopen을 on으로 해주시기 바랍니다.
	$object = simplexml_load_string($xml);

	if(count($object->body[0]->items[0]->item) == 0){
?>
	<h3>조회한 정보가 없습니다.</h3>
<?PHP
	}else{
?>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<tr>
<?PHP
		foreach($object->body[0]->items[0]->item as $item){
			//농작업 일정 항목명
			$codeNm = $item->codeNm;
			//일정코드
			$kidofcomdtySeCode = $item->kidofcomdtySeCode;
?>
			<td width="10%" align="center"><a href="javascript:fncNextList('<?=$kidofcomdtySeCode?>','<?=$codeNm?>');"><?=$codeNm?></a></td>
<?PHP
		}
?>
		<tr>
	</table>
<?PHP
	}
}
?>

<!-- =================================================== 메인 카테고리 끝 ================================================================================ -->

<!-- =================================================== 세부항목 리스트 시작 ================================================================================ -->

<?PHP
//일정별 리스트
if(isset($_REQUEST["listCategoryCode"])){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "farmWorkingPlanNew";
	//오퍼레이션 명
	$operationName = "workScheduleLst";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;

	if($_REQUEST["listCategoryCode"]!=NULL){
		$parameter .= "&kidofcomdtySeCode=";
		$parameter .= $_REQUEST["listCategoryCode"];
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
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
<?PHP
		foreach($object->body[0]->items[0]->item as $item){
			//파일 링크
			$fileDownUrlInfo = $item->fileDownUrlInfo;
			//파일 원본 이름
			$orginlFileNm = $item->orginlFileNm;
			//확장자명을 제외한 파일 이름
			$sj = $item->sj;
			//키값
			$cntntsNo = $item->cntntsNo;
?>
		<tr>
		    <td width="50%"><a href="javascript:;move('<?=$cntntsNo?>','<?=$sj?>');"><?=$sj?></a></td>
		    <td width="50%"><a href="<?=$fileDownUrlInfo?>">파일다운로드</a></td>
		</tr>
<?PHP
		}
?>
	</table>
<?PHP
	}
}
?>
<!-- =================================================== 세부항목 리스트 끝 ================================================================================ -->
</body>
</html>
