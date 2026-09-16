<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>품종 정보</title>
<script type='text/javascript'>

//메인 카테고리 항목
function mainMove(){
	with(document.searchInsttForm){
		method="post";
		action = "varietyInfo.php";
		target = "_self";
		submit();
	}
}

//세부항목 리스트 이동
function fncNextList(cCode){
	with(document.apiForm){
		categoryCode.value = cCode;
		method="post";
		action = "varietyInfo.php";
		target = "_self";
		submit();
	}
}

//검색
function fncSearch(flag){
	
	if(flag==2) {
		document.searchApiForm.sMtrtSeCode.value = '';
		document.searchApiForm.sSkllSeCode.value = '';
		document.searchApiForm.sGrdlSeCode.value = '';
	}
	
	with(document.searchApiForm){
		method="post";
		action = "varietyInfo.php";
		target = "_self";
		submit();
	}
}

//페이지 이동
function fncGoPage(page){
	with(document.apiForm){
		pageNo.value = page;
		method="post";
		action = "varietyInfo.php";
		target = "_self";
		submit();
	}
}

</script>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>품종 정보</strong></h3><hr>

<?PHP
//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
$apiKey = "발급받은인증키";

//서비스 명
$serviceName = "varietyInfo";

//카테고리 코드
$categoryCodeVal="";
if(isset($_REQUEST["categoryCode"])){
	$categoryCodeVal = $_REQUEST["categoryCode"];
}

//기관코드 등록
$insttCode = "";
if(isset($_REQUEST["insttCode"])){
	$insttCode = $_REQUEST["insttCode"];
}

//기관명
$insttName = "";
if(isset($_REQUEST["insttName"])){
	$insttName = $_REQUEST["insttName"];
}

?>

<form name="apiForm">
	<input type="hidden" name="categoryCode" value="<?=$categoryCodeVal?>">
	<input type="hidden" name="insttName" value="<?=$insttName?>">
	<input type="hidden" name="insttCode" value="<?=$insttCode?>">
	<input type="hidden" name="pageNo">
</form>

<?PHP

//기관 코드
if(true){
	//오퍼레이션 명
	$operationName = "insttList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;
	$parameter .= "&insttCode=".$insttCode;

	
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
	<form name="searchInsttForm">
	<input type="hidden" name="insttCode" value="<?=$insttCode?>">
		기관명&nbsp;
		<select name="insttName" onchange="mainMove();">
		<option value="">선택하세요</option>
<?PHP
		foreach($object->body[0]->items[0]->item as $item){
			//대분류 카테고리 명
			$codeNm = $item->codeNm;
?>
				<option value="<?=$codeNm?>" <?PHP if(isset($_REQUEST["insttName"])){ if($_REQUEST["insttName"]==$codeNm) echo "selected"; }?>> <?=$codeNm?></option>
<?PHP
		}
?>
		</select>
	</form>	
<?PHP
	}
}
?>


<?PHP
//메인 카테고리 리스트
	//오퍼레이션 명
	$operationName = "mainCategoryList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;
	$parameter .= "&insttCode=".$insttCode;
	$parameter .= "&insttName=" . urlencode($insttName);
	
	$url = "http://api.nongsaro.go.kr/service" . $parameter; 

	//XML Parsing
	$xml1 = file_get_contents($url);
	//PHP5.x 이상이 설치되어 있어야 하며, php.ini에 allow_url_fopen을 on으로 해주시기 바랍니다.
	$object1 = simplexml_load_string($xml1);
	
	if(count($object1->body[0]->items[0]->item) == 0){
?>
	<hr>
	<h3>조회한 정보가 없습니다.</h3>
<?PHP
	}else{
		if($categoryCodeVal == null || $categoryCodeVal == ""){
			$categoryCodeVal = $object1->body[0]->items[0]->item[0]->categoryCode;
		}
?>
	<hr>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<tr>
<?PHP
		foreach($object1->body[0]->items[0]->item as $item){
			//카테고리 코드
			$categoryCode = $item->categoryCode;
			//카테고리 명
			$categoryNm = $item->categoryNm;
?>
			<td align="center">
				<a href="javascript:fncNextList('<?=$categoryCode?>');">  <?PHP if ($categoryCode==$categoryCodeVal) { ?> <strong> <?=$categoryNm?> </strong> <?PHP }else{ ?> <?=$categoryNm?> <?PHP } ?> </a>
			</td>
<?PHP
		}
?>
		<tr>
	</table>
<?PHP
	}
?>

<?PHP
	//오퍼레이션 명
	$operationName = "middleCategoryList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;
	$parameter .= "&categoryCode=" . $categoryCodeVal;
	$parameter .= "&insttCode=".$insttCode;
	$parameter .= "&insttName=" . urlencode($insttName);
	
	$url = "http://api.nongsaro.go.kr/service" . $parameter; 

	//XML Parsing
	$xml2 = file_get_contents($url);
	$object2 = simplexml_load_string($xml2);

	$fCropsCode = "";
	$fSvcCodeNm = "";
	
	if(count($object2->body[0]->items[0]->item) == 0){
?>
	<h3>조회한 정보가 없습니다.</h3>
<?PHP
	}else{
?>
	<hr>
	<form name="searchApiForm">
	<input type="hidden" name="insttName" value="<?=$insttName?>">
	<input type="hidden" name="insttCode" value="<?=$insttCode?>">
	<input type="hidden" name="categoryCode" value="<?=$categoryCodeVal?>">
	<table width="100%" cellSpacing="0" cellPadding="0">
		<tr>
			<td width="85%">
				<select name="sType">
					<option value="sCntntsSj"  <?PHP if(isset($_REQUEST["sType"])){ if($_REQUEST["sType"]=="sCntntsSj") echo "selected"; }?>>품종명</option>
					<option value="sMainChartrInfo" <?PHP if(isset($_REQUEST["sType"])){ if($_REQUEST["sType"]=="sMainChartrInfo") echo "selected"; }?>>주요특성</option>
					<?PHP if( $categoryCodeVal == "FC" ) { ?>
					<option value="sSvcCodeNm" <?PHP if(isset($_REQUEST["sType"])){ if($_REQUEST["sType"]=="sSvcCodeNm") echo "selected"; }?>>작물명</option>
					<?PHP } ?>
				</select> 
				
				<?PHP if(isset($_REQUEST["sText"])){ ?>
				<input type="text" name="sText" value="<?=$_REQUEST["sText"]?>">&nbsp;&nbsp;&nbsp;&nbsp;
				<?PHP }else{ ?>
				<input type="text" name="sText" >&nbsp;&nbsp;&nbsp;&nbsp;
				<?PHP } ?>
				
				<?PHP if( $categoryCodeVal!="FC" ) { ?>
				작물명&nbsp;
				<select name="svcCodeNm">
				
<?PHP
					foreach($object2->body[0]->items[0]->item as $item){
						//코드
						$code = $item->code;
						//코드명
						$codeNm = $item->codeNm;
						//구분
						$gubn = $item->gubn;
						
						if($gubn=="CROP"){
							if($fSvcCodeNm==""){
								$fSvcCodeNm = $codeNm; 
							}

?>
				<option value="<?=$codeNm?>" <?PHP if(isset($_REQUEST["svcCodeNm"])){ if($_REQUEST["svcCodeNm"]==$codeNm) echo "selected"; }?>> <?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
<?PHP
				}
?>
				<?PHP if( $categoryCodeVal=="FC" ) { ?>
				작물분류&nbsp;
				<select name="sCropsCode"  onchange="fncSearch(2);" >
<?PHP
					foreach($object2->body[0]->items[0]->item as $item){
						$code = $item->code;
						$codeNm = $item->codeNm;
						$gubn = $item->gubn;
						
						if($gubn=="CLASS1"){
							if($fCropsCode==""){
								$fCropsCode = $code; 
							}
?>
							<option value="<?=$code?>" <?PHP if(isset($_REQUEST["sCropsCode"])){ if($_REQUEST["sCropsCode"]==$code) echo "selected"; }?>><?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
<?PHP
				}
?>
				육성년도 &nbsp;
				<select name="sUnbrngYear">
				<option value="">선택하세요</option>
<?PHP
					foreach($object2->body[0]->items[0]->item as $item){
						$code = $item->code;
						$codeNm = $item->codeNm;
						$gubn = $item->gubn;
						
						if($gubn=="YEAR"){
?>
							<option value="<?=$code?>" <?PHP if(isset($_REQUEST["sUnbrngYear"])){ if($_REQUEST["sUnbrngYear"]==$code) echo "selected"; }?>><?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
		    </td>
		    <td width="15%" align="right">
				<input type="button" name="search" value="조회" onclick="fncSearch(1);"/>
		    </td>
		</tr>
<?PHP
		}
?>

<?PHP
if($categoryCodeVal != null && $categoryCodeVal != ""){
	
	if($categoryCodeVal=="FC"){
		//오퍼레이션 명
		$operationName = "subCategoryList";
		
		//XML 받을 URL 생성
		$parameter = "/".$serviceName."/".$operationName;
		$parameter .= "?apiKey=".$apiKey;
		$parameter .= "&categoryCode=".$categoryCodeVal;
		$parameter .= "&insttCode=".$insttCode;
		$parameter .= "&insttName=" . urlencode($insttName);
		
		if(isset($_REQUEST["sCropsCode"])){
			$parameter .= "&sCropsCode=";
			$parameter .= $_REQUEST["sCropsCode"];
		}else{
			$parameter .= "&sCropsCode=" . $fCropsCode;
		}		
		
		$url = "http://api.nongsaro.go.kr/service" . $parameter; 
	
		//XML Parsing
		$xml3 = file_get_contents($url);
		$object3 = simplexml_load_string($xml3);
?>
		<tr>
			<td width="85%">
				숙기&nbsp;
				<select name="sMtrtSeCode">
				<option value="">선택하세요</option>
<?PHP
					foreach($object3->body[0]->items[0]->item as $item){
						//코드
						$code = $item->code;
						//코드명
						$codeNm = $item->codeNm;
						//분류 코드
						$codeGroup = $item->codeGroup;
						
						if($codeGroup=="220"){
?>
							<option value="<?=$code?>" <?PHP if(isset($_REQUEST["sMtrtSeCode"])){ if($_REQUEST["sMtrtSeCode"]==$code) echo "selected"; }?>><?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
				구분&nbsp;
				<select name="sSkllSeCode">
				<option value="">선택하세요</option>
<?PHP
					foreach($object3->body[0]->items[0]->item as $item){
						$code = $item->code;
						$codeNm = $item->codeNm;
						$codeGroup = $item->codeGroup;
						
						if($codeGroup=="218"){
?>
							<option value="<?=$code?>" <?PHP if(isset($_REQUEST["sSkllSeCode"])){ if($_REQUEST["sSkllSeCode"]==$code) echo "selected"; }?>><?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
				지대&nbsp;
				<select name="sGrdlSeCode">
				<option value="">선택하세요</option>
<?PHP
					foreach($object3->body[0]->items[0]->item as $item){
						$code = $item->code;
						$codeNm = $item->codeNm;
						$codeGroup = $item->codeGroup;
						
						if($codeGroup=="219"){
?>
							<option value="<?=$code?>" <?PHP if(isset($_REQUEST["sSkllSeCode"])){ if($_REQUEST["sSkllSeCode"]==$code) echo "selected"; }?>><?=$codeNm?></option>
<?PHP
						}
					}
?>
				</select>&nbsp;&nbsp;&nbsp;&nbsp;
		    </td>
		</tr>
<?PHP
				}
			}
?>
	</table>
	</form>

<?PHP
//품종 정보 리스트
if($categoryCodeVal != null && $categoryCodeVal != ""){
	//오퍼레이션 명
	$operationName = "varietyList";

	//XML 받을 URL 생성
	$parameter = "/".$serviceName."/".$operationName;
	$parameter .= "?apiKey=".$apiKey;
	$parameter .= "&insttCode=".$insttCode;
	$parameter .= "&insttName=" . urlencode($insttName);
	
	if($categoryCodeVal == "FC"){
		//작물분류 검색
		if(isset($_REQUEST["sCropsCode"])){
			$parameter .= "&sCropsCode=";
			$parameter .= $_REQUEST["sCropsCode"];
		}else{
			$parameter .= "&sCropsCode=" . $fCropsCode;
		}
		//숙기 검색
		if(isset($_REQUEST["sMtrtSeCode"])){
			$parameter .= "&sMtrtSeCode=";
			$parameter .= $_REQUEST["sMtrtSeCode"];
		}
		//기능구분 검색
		if(isset($_REQUEST["sSkllSeCode"])){
			$parameter .= "&sSkllSeCode=";
			$parameter .= $_REQUEST["sSkllSeCode"];
		}
		//지대 검색
		if(isset($_REQUEST["sGrdlSeCode"])){
			$parameter .= "&sGrdlSeCode=";
			$parameter .= $_REQUEST["sGrdlSeCode"];
		}
		//품종 검색
		if(isset($_REQUEST["sText"])){
			$parameter .= "&sText=";
			$parameter .= $_REQUEST["sText"];
			$parameter .= "&sType=";
			$parameter .= $_REQUEST["sType"];
		}
		//육성년도 검색
		if(isset($_REQUEST["sUnbrngYear"])){
			$parameter .= "&sUnbrngYear=";
			$parameter .= $_REQUEST["sUnbrngYear"];
		}
	}else{
		//품종 검색
		if(isset($_REQUEST["sText"])){
			$parameter .= "&sText=";
			$parameter .= $_REQUEST["sText"];
			$parameter .= "&sType=";
			$parameter .= $_REQUEST["sType"];
		}
		//작물명 검색
		if(isset($_REQUEST["svcCodeNm"])){
			$parameter .= "&svcCodeNm=";
			$parameter .= $_REQUEST["svcCodeNm"];
		}else{
			$parameter .= "&svcCodeNm=" . $fSvcCodeNm;
		}
		//육성년도 검색
		if(isset($_REQUEST["sUnbrngYear"])){
			$parameter .= "&sUnbrngYear=";
			$parameter .= $_REQUEST["sUnbrngYear"];
		}
	}

	if(isset($_REQUEST["categoryCode"])){
		$parameter .= "&categoryCode=";
		$parameter .= $_REQUEST["categoryCode"];
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
			<col width="1%"/>
			<col width="10%"/>
			<col width="10%"/>
			<col width="10%"/>
			<col width="10%"/>
			<col width="35%"/>
		</colgroup>
		<tr>
			<th>사진</th>
			<th>작물명</th>
			<th>육성년도</th>
			<th>육성기관</th>
			<th>품종명</th>
			<th>주요특성</th>
		</tr>
<?PHP
		foreach($object->body[0]->items[0]->item as $item){
			//서비스 코드명
			$svcCodeNm = $item->svcCodeNm;
			//육성년도
			$unbrngYear = $item->unbrngYear;
			//육성 기관 정보
			$unbrngInsttInfo = $item->unbrngInsttInfo;
			//컨텐츠 제목
			$cntntsSj = $item->cntntsSj;
			//주요 특성 정보
			$mainChartrInfo = $item->mainChartrInfo;
			//파일 경로
			$atchFileLink = $item->atchFileLink;
			//파일 명
			$orginlFileNm = $item->orginlFileNm;
			//이미지 경로
			$imgFileLink = $item->imgFileLink;
?>
		<tr>
		    <td><img src="<?=$imgFileLink?>" width="128" height="103"></img></td>
   			<td><?=$svcCodeNm?></td>
   			<td><?=$unbrngYear?></td>
   			<td><?=$unbrngInsttInfo?></td>
   			<td><a href="<?=$atchFileLink?>"><?=$cntntsSj?></a></td>
   			<td><?=$mainChartrInfo?></td>
		</tr>
<?PHP
		}
?>
	</table>
<?PHP
	}
	
	$numOfRows = $object->body[0]->items[0]->numOfRows;
	$totalCount = $object->body[0]->items[0]->totalCount;
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
}
?>
</body>
</html>