<?php
error_reporting(E_ALL);
ini_set("display_errors", 1);
?>

<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>농작업일정</title>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>농작업일정</strong></h3>
<hr>
<?PHP
//농작업일정 상세조회
if(isset($_REQUEST["cntntsNo"])){

	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "farmWorkingPlanNew";
	//오퍼레이션 명
	$operationName = "workScheduleEraInfoLst";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;

	if($_REQUEST["cntntsNo"]!=NULL){
		$parameter .= "&cntntsNo=";
		$parameter .= $_REQUEST["cntntsNo"];
	}


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
	<div>
<?PHP
			$htmlCn = $object->body[0]->items[0]->item[0]->htmlCn;
?>
			<?=$htmlCn?>
	</div>
<?PHP
	}


	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	$apiKey = "발급받은인증키를삽입하세요";
	//서비스 명
	$serviceName = "farmWorkingPlanNew";
	//오퍼레이션 명
	$operationName = "workScheduleDtl";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;

	if($_REQUEST["cntntsNo"]!=NULL){
		$parameter .= "&cntntsNo=";
		$parameter .= $_REQUEST["cntntsNo"];
	}

	$url = "http://api.nongsaro.go.kr/service" . $parameter;

	//XML Parsing
	$xml = file_get_contents($url);
	//PHP5.x 이상이 설치되어 있어야 하며, php.ini에 allow_url_fopen을 on으로 해주시기 바랍니다.
	$object = simplexml_load_string($xml);

	//내용
	$cn = $object->body[0]->item[0]->cn;
	$cn = str_replace("<table", "<table border=\"1\" cellspacing=\"0\" cellpadding=\"0\"",$cn);
?>
	<div>
		<?=$cn?>
	</div>
<?PHP
}
?>
<br>
<input type="button" onclick="javascript:location.href='farmWorkingPlan.php'" value="처음화면으로"/>&nbsp;
</body>
</html>