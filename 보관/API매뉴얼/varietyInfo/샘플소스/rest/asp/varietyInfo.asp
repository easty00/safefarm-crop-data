<% @CODEPAGE="65001" language="VBScript" %>
<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>품종 정보</title>
<script type='text/javascript'>

//메인 카테고리 항목
function mainMove(){
	with(document.searchInsttForm){
		method="post";
		action = "varietyInfo.asp";
		target = "_self";
		submit();
	}
}
//세부항목 리스트 이동
function fncNextList(cCode){
	with(document.apiForm){
		categoryCode.value = cCode;
		method="post";
		action = "varietyInfo.asp";
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
		action = "varietyInfo.asp";
		target = "_self";
		submit();
	}
}

//페이지 이동
function fncGoPage(page){
	with(document.apiForm){
		pageNo.value = page;
		method="post";
		action = "varietyInfo.asp";
		target = "_self";
		submit();
	}
}

</script>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>품종 정보</strong></h3><hr>
<%
'apiKey - 농사로 Open API에서 신청 후 승인되면 확인가능
apiKey = "발급받은인증키"

'서비스 명
serviceName = "varietyInfo"

'카테고리 코드
categoryCodeVal = ""
If Not Request("categoryCode") Is Nothing And Request("categoryCode") <> "" Then
	categoryCodeVal=Request("categoryCode")
End If

'기관코드 등록
insttCode = ""
If Not Request("insttCode") Is Nothing And Request("insttCode") <> "" Then
	insttCode = Request("insttCode")
End If

'기관명
insttName = ""
If Not Request("insttName") Is Nothing And Request("insttName") <> "" Then
	insttName = Request("insttName")
End If
%>

<form name="apiForm">
	<input type="hidden" name="categoryCode" value="<%=categoryCodeVal%>">
	<input type="hidden" name="insttName" value="<%=insttName%>">
	<input type="hidden" name="insttCode" value="<%=insttCode%>">
	<input type="hidden" name="pageNo">
</form>

<%

'기관 코드
If true Then
	'오퍼레이션 명
	operationName = "insttList"
	
	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey="&apiKey
	parameter = parameter & "&insttCode="&insttCode
	
	targetURL = "http://api.nongsaro.go.kr/service" & parameter
	
	'농사로 Open API 통신 시작
	Set xmlHttp = Server.CreateObject("Microsoft.XMLHTTP")    
	xmlHttp.Open "GET", targetURL, False   
	xmlHttp.Send    
	
	Set oStream = CreateObject("ADODB.Stream")   
	oStream.Open   
	oStream.Position = 0   
	oStream.Type = 1   
	oStream.Write xmlHttp.ResponseBody   
	oStream.Position = 0   
	oStream.Type = 2   
	oStream.Charset = "utf-8"   
	sText = oStream.ReadText   
	oStream.Close   
	
	Set xmlDOM = server.CreateObject("MSXML.DOMDOCUMENT")   
	xmlDOM.async = False    
	xmlDOM.LoadXML sText   
	'농사 Open API 통신 끝
	     
	Set listItem = xmlDOM.SelectNodes("//items")
	cnt = listItem(0).childNodes.length
	Set items = listItem(0).childNodes

	If cnt=0 Then
		Response.Write("<h3><font color='red'>조회한 정보가 없습니다.</font></h3>")
	Else
%>
	<form name="searchInsttForm">
	<input type="hidden" name="insttCode" value="<%=insttCode%>">
		기관명&nbsp;
		<select name="insttName" onchange="mainMove();">
		<option value="">선택하세요</option>
<%
		For i=0 To cnt-1
		   Set itemNode = items.item(i)
			If NOT itemNode Is Nothing Then
				'기관명
				If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
					codeNm = itemNode.SelectSingleNode("codeNm").text
				End If
			End If
%>
			<option value="<%=codeNm%>" <%If codeNm = insttName Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
		   Set itemNode = Nothing
		Next
	Response.Write("</select></form>")
	End If
End If
%>

<%
'메인 카테고리 리스트
	'오퍼레이션 명
	operationName = "mainCategoryList"
	
	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey="&apiKey
	parameter = parameter & "&insttCode=" & insttCode
	parameter = parameter & "&insttName=" & Server.URLEncode(insttName)

	targetURL = "http://api.nongsaro.go.kr/service" & parameter
	
	'농사로 Open API 통신 시작
	Set xmlHttp1 = Server.CreateObject("Microsoft.XMLHTTP")    
	xmlHttp1.Open "GET", targetURL, False   
	xmlHttp1.Send    
	
	Set oStream1 = CreateObject("ADODB.Stream")   
	oStream1.Open   
	oStream1.Position = 0   
	oStream1.Type = 1   
	oStream1.Write xmlHttp1.ResponseBody   
	oStream1.Position = 0   
	oStream1.Type = 2   
	oStream1.Charset = "utf-8"   
	sText = oStream1.ReadText   
	oStream1.Close   
	
	Set xmlDOM1 = server.CreateObject("MSXML.DOMDOCUMENT")   
	xmlDOM1.async = False    
	xmlDOM1.LoadXML sText   
	'농사 Open API 통신 끝
	     
	Set listItem1 = xmlDOM1.SelectNodes("//items")
	cnt = listItem1(0).childNodes.length
	Set items1 = listItem1(0).childNodes

	If cnt = 0 Then
		Response.Write("<h3>조회한 정보가 없습니다.</h3>")
	Else
		If Request("categoryCode") Is Nothing Or Request("categoryCode") = "" Then
		    Set codeitemNode = items1.item(0)
			categoryCodeVal=codeitemNode.SelectSingleNode("categoryCode").text
		End If
%>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<tr>
<%
		For i=0 To cnt-1
		   Set itemNode = items1.item(i)
			If NOT itemNode Is Nothing Then
				'카테고리 명
				If NOT itemNode.SelectSingleNode("categoryNm") is Nothing Then
					categoryNm = itemNode.SelectSingleNode("categoryNm").text
				End If
				'카테고리 코드
				If NOT itemNode.SelectSingleNode("categoryCode") is Nothing Then
					categoryCode = itemNode.SelectSingleNode("categoryCode").text
				End If
			End If
%>
			<td align="center">
				<a href="javascript:fncNextList('<%=categoryCode%>');">  <% If  categoryCode=categoryCodeVal Then  %> <strong> <%=categoryNm%> </strong> <% Else %> <%=categoryNm%> <% End If %>  </a>
			</td>
<%
		   Set itemNode = Nothing
		Next
		Response.Write("</tr></table>")
	End If
%>

<%

	'오퍼레이션 명
	operationName = "middleCategoryList"
	
	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey=" & apiKey
	parameter = parameter & "&categoryCode=" & categoryCodeVal
	parameter = parameter & "&insttCode="&insttCode
	parameter = parameter & "&insttName=" & Server.URLEncode(insttName)
	
	targetURL = "http://api.nongsaro.go.kr/service" & parameter
	
	'농사로 Open API 통신 시작
	Set xmlHttp2 = Server.CreateObject("Microsoft.XMLHTTP")    
	xmlHttp2.Open "GET", targetURL, False   
	xmlHttp2.Send    
	
	Set oStream2 = CreateObject("ADODB.Stream")   
	oStream2.Open   
	oStream2.Position = 0   
	oStream2.Type = 1   
	oStream2.Write xmlHttp2.ResponseBody   
	oStream2.Position = 0   
	oStream2.Type = 2   
	oStream2.Charset = "utf-8"   
	sText = oStream2.ReadText   
	oStream2.Close   
	
	Set xmlDOM2 = server.CreateObject("MSXML.DOMDOCUMENT")   
	xmlDOM2.async = False    
	xmlDOM2.LoadXML sText   
	'농사 Open API 통신 끝
	
	Set listItem2 = xmlDOM2.SelectNodes("//items")
	middleCnt = listItem2(0).childNodes.length
	Set items2 = listItem2(0).childNodes
	
	fSvcCodeNm = ""
	fCropsCode = ""
	
	If cnt = 0 Then
		Response.Write("<h3>조회한 정보가 없습니다.</h3>")
	Else
%>
	<hr>
	<form name="searchApiForm">
	<input type="hidden" name="insttName" value="<%=insttName%>">
	<input type="hidden" name="insttCode" value="<%=insttCode%>">
	<input type="hidden" name="categoryCode" value="<%=categoryCodeVal%>">
	<table width="100%" cellSpacing="0" cellPadding="0">
		<tr>
			<td width="85%">
				<select name="sType">
					<option value="sCntntsSj"  <%If Request("sType")="sCntntsSj"  Then Response.Write("selected") Else Response.Write("") End If%>>품종명</option>
					<option value="sMainChartrInfo" <%If Request("sType")="sMainChartrInfo"  Then Response.Write("selected") Else Response.Write("") End If%>>주요특성</option>
					<% If categoryCodeVal = "FC" Then %>
					<option value="sSvcCodeNm" <%If Request("sType")="sSvcCodeNm"  Then Response.Write("selected") Else Response.Write("") End If%>>작물명</option>
					<% End If %>
				</select> 
<%				If Not Request("sText") Is Nothing And Request("sText") <> "" Then %>
					<input type="text" name="sText" value="<%=request("sText")%>">&nbsp;&nbsp;&nbsp;&nbsp;
<%				Else %>
					<input type="text" name="sText" >&nbsp;&nbsp;&nbsp;&nbsp;
<%				End If %>
				
<%				If NOT categoryCodeVal = "FC" Then %>
				작물명&nbsp;
				<select name="svcCodeNm">
				
<%
					For i=0 To middleCnt-1
						Set itemNode = items2.item(i)
						If NOT itemNode Is Nothing Then
							'코드
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							'코드 명
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							'구분
							If NOT itemNode.SelectSingleNode("gubn") is Nothing Then
								gubn = itemNode.SelectSingleNode("gubn").text
							End If
						End If
							
						If gubn="CROP" Then
							If fSvcCodeNm = "" Then
								fSvcCodeNm = codeNm
							End If
%>
							<option value="<%=codeNm%>" <%If Request("svcCodeNm")=codeNm Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
				End If
%>
<%				If categoryCodeVal = "FC" Then %>
				작물분류&nbsp;
				<select name="sCropsCode"  onchange="fncSearch(2);" >
<%
					For i=0 To middleCnt-1
						Set itemNode = items2.item(i)
						If NOT itemNode Is Nothing Then
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							If NOT itemNode.SelectSingleNode("gubn") is Nothing Then
								gubn = itemNode.SelectSingleNode("gubn").text
							End If
						End If
							
						If gubn="CLASS1" Then
							If fCropsCode = "" Then
								fCropsCode = code
							End If
%>
							<option value="<%=code%>" <%If Request("sCropsCode")=code Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
				End If
%>
				육성년도 &nbsp;
				<select name="sUnbrngYear">
				<option value="">선택하세요</option>
<%
					For i=0 To middleCnt-1
						Set itemNode = items2.item(i)
						If NOT itemNode Is Nothing Then
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							If NOT itemNode.SelectSingleNode("gubn") is Nothing Then
								gubn = itemNode.SelectSingleNode("gubn").text
							End If
						End If
							
						If gubn="YEAR" Then
%>
							<option value="<%=code%>" <%If Request("sUnbrngYear")=code Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
%>
		    </td>
		    <td width="15%" align="right">
				<input type="button" name="search" value="조회" onclick="fncSearch(1);"/>
		    </td>
		</tr>
<%
		End If
%>

<%
If categoryCodeVal <> "" Then
	If categoryCodeVal = "FC" Then
		'오퍼레이션 명
		operationName = "subCategoryList"
		
		'XML 받을 URL 생성
		parameter = "/" & serviceName & "/" & operationName
		parameter = parameter & "?apiKey=" & apiKey
		parameter = parameter & "&categoryCode=" & categoryCodeVal
		parameter = parameter & "&insttCode="&insttCode
		parameter = parameter & "&insttName=" & Server.URLEncode(insttName)
		
		If Not Request("sCropsCode") Is Nothing OR Request("sCropsCode") <> "" Then
			parameter = parameter & "&sCropsCode=" & Request("sCropsCode")
		Else
			parameter = parameter & "&sCropsCode=" & fCropsCode
		End If
		
		targetURL = "http://api.nongsaro.go.kr/service" & parameter
		
		'농사로 Open API 통신 시작
		Set xmlHttp3 = Server.CreateObject("Microsoft.XMLHTTP")    
		xmlHttp3.Open "GET", targetURL, False   
		xmlHttp3.Send    
		
		Set oStream3 = CreateObject("ADODB.Stream")   
		oStream3.Open   
		oStream3.Position = 0   
		oStream3.Type = 1   
		oStream3.Write xmlHttp3.ResponseBody   
		oStream3.Position = 0   
		oStream3.Type = 2   
		oStream3.Charset = "utf-8"   
		sText = oStream3.ReadText   
		oStream3.Close   
		
		Set xmlDOM3 = server.CreateObject("MSXML.DOMDOCUMENT")   
		xmlDOM3.async = False    
		xmlDOM3.LoadXML sText   
		'농사 Open API 통신 끝
		
		Set listItem3 = xmlDOM3.SelectNodes("//items")
		cnt = listItem3(0).childNodes.length
		Set items3 = listItem3(0).childNodes
%>
		<tr>
			<td width="85%">
				숙기&nbsp;
				<select name="sMtrtSeCode">
				<option value="">선택하세요</option>
<%
					For i=0 To cnt-1
					   Set itemNode = items3.item(i)
						If NOT itemNode Is Nothing Then
							'코드
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							'코드 명
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							'분류 코드
							If NOT itemNode.SelectSingleNode("codeGroup") is Nothing Then
								codeGroup = itemNode.SelectSingleNode("codeGroup").text
							End If
						End If
						If codeGroup = "220" Then
%>
				<option value="<%=code%>" <%If Request("sMtrtSeCode")=code Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
%>
				구분&nbsp;
				<select name="sSkllSeCode">
				
				<option value="">선택하세요</option>
<%
					For i=0 To cnt-1
					   Set itemNode = items3.item(i)
						If NOT itemNode Is Nothing Then
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							If NOT itemNode.SelectSingleNode("codeGroup") is Nothing Then
								codeGroup = itemNode.SelectSingleNode("codeGroup").text
							End If
						End If
						If codeGroup = "218" Then
%>
				<option value="<%=code%>" <%If Request("sSkllSeCode")=code Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
%>
				지대&nbsp;
				<select name="sGrdlSeCode">
				<option value="">선택하세요</option>
<%
					For i=0 To cnt-1
					   Set itemNode = items3.item(i)
						If NOT itemNode Is Nothing Then
							If NOT itemNode.SelectSingleNode("code") is Nothing Then
								code = itemNode.SelectSingleNode("code").text
							End If
							If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
								codeNm = itemNode.SelectSingleNode("codeNm").text
							End If
							If NOT itemNode.SelectSingleNode("codeGroup") is Nothing Then
								codeGroup = itemNode.SelectSingleNode("codeGroup").text
							End If
						End If
						If codeGroup = "219" Then
%>
				<option value="<%=code%>" <%If Request("sGrdlSeCode")=code Then Response.Write("selected") Else Response.Write("") End If%>><%=codeNm%></option>
<%
						End If
						Set itemNode = Nothing
					Next
					Response.Write("</select>&nbsp;&nbsp;&nbsp;&nbsp;")
%>
		    </td>
		</tr>
<%
	End If
End If
%>
	</table>
	</form>


<%
'품종 정보 리스트
If categoryCodeVal <> "" Then
	'오퍼레이션 명
	operationName = "varietyList"
	
	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey=" & apiKey
	parameter = parameter & "&categoryCode=" & categoryCodeVal
	parameter = parameter & "&pageNo=" & Request("pageNo")
	parameter = parameter & "&insttCode="&insttCode
	parameter = parameter & "&insttName=" & Server.URLEncode(insttName)
	
	If categoryCodeVal = "FC" Then
		'작물분류 검색
		If Not Request("sCropsCode") Is Nothing And Request("sCropsCode") <> "" Then
			parameter = parameter & "&sCropsCode=" & Server.URLEncode(Request("sCropsCode"))
		Else
			parameter = parameter & "&sCropsCode=" & fCropsCode
		End If
		'숙기 검색
		If Not Request("sMtrtSeCode") Is Nothing And Request("sMtrtSeCode") <> "" Then
			parameter = parameter & "&sMtrtSeCode=" & Server.URLEncode(Request("sMtrtSeCode"))
		End If
		'기능구분 검색
		If Not Request("sSkllSeCode") Is Nothing And Request("sSkllSeCode") <> "" Then
			parameter = parameter & "&sSkllSeCode=" & Server.URLEncode(Request("sSkllSeCode"))
		End If
		'지대 검색
		If Not Request("sGrdlSeCode") Is Nothing And Request("sGrdlSeCode") <> "" Then
			parameter = parameter & "&sGrdlSeCode=" & Server.URLEncode(Request("sGrdlSeCode"))
		End If
		'품종 검색	
		If Not Request("sText") Is Nothing And Request("sText") <> "" Then
			parameter = parameter & "&sText=" & Server.URLEncode(Request("sText"))
			parameter = parameter & "&sType=" & Server.URLEncode(Request("sType"))
		End If
		'육성년도 검색
		If Not Request("sUnbrngYear") Is Nothing And Request("sUnbrngYear") <> "" Then
			parameter = parameter & "&sUnbrngYear=" & Server.URLEncode(Request("sUnbrngYear"))
		End If
	Else
		'품종 검색	
		If Not Request("sText") Is Nothing And Request("sText") <> "" Then
			parameter = parameter & "&sText=" & Server.URLEncode(Request("sText"))
			parameter = parameter & "&sType=" & Server.URLEncode(Request("sType"))
		End If
		'작물명 검색
		If Not Request("svcCodeNm") Is Nothing And Request("svcCodeNm") <> "" Then
			parameter = parameter & "&svcCodeNm=" & Server.URLEncode(Request("svcCodeNm"))
		Else
			parameter = parameter & "&svcCodeNm=" & Server.URLEncode(fSvcCodeNm)
		End If
		'육성년도 검색
		If Not Request("sUnbrngYear") Is Nothing And Request("sUnbrngYear") <> "" Then
			parameter = parameter & "&sUnbrngYear=" & Server.URLEncode(Request("sUnbrngYear"))
		End If
	End If
		
	
	targetURL = "http://api.nongsaro.go.kr/service" & parameter
	
	'농사로 Open API 통신 시작
	Set xmlHttp = Server.CreateObject("Microsoft.XMLHTTP")    
	xmlHttp.Open "GET", targetURL, False   
	xmlHttp.Send    
	
	Set oStream = CreateObject("ADODB.Stream")   
	oStream.Open   
	oStream.Position = 0   
	oStream.Type = 1   
	oStream.Write xmlHttp.ResponseBody   
	oStream.Position = 0   
	oStream.Type = 2   
	oStream.Charset = "utf-8"   
	sText = oStream.ReadText   
	oStream.Close   
	
	Set xmlDOM = server.CreateObject("MSXML.DOMDOCUMENT")   
	xmlDOM.async = False    
	xmlDOM.LoadXML sText   
	'농사 Open API 통신 끝
	
	Set listItem = xmlDOM.SelectNodes("//items")
	cnt = listItem(0).childNodes.length
	Set items = listItem(0).childNodes
	
'페이징 처리를 위한 값 받기
	'한 페이지에 제공할 건수
	Set numOfRows = xmlDOM.SelectNodes("//numOfRows")
	If Not numOfRows(0) Is Nothing Then numOfRowsText= numOfRows(0).Text Else numOfRowsText = "10" End If
	'조회할 페이지 번호
	Set pageNo = xmlDOM.SelectNodes("//pageNo")
	If Not pageNo(0) Is Nothing Then pageNoText= pageNo(0).Text Else pageNoText = "1" End If
	'조회된 총 건수
	Set totalCount = xmlDOM.SelectNodes("//totalCount")
	If Not totalCount(0) Is Nothing Then totalCountText= totalCount(0).Text Else totalCountText = "" End If
	
	If cnt-3 = 0 Then
		Response.Write("<h3>조회한 정보가 없습니다.</h3>")
	Else
%>
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
<%
		For i=0 To cnt-4
		   Set itemNode = items.item(i)
			If NOT itemNode Is Nothing Then
				'서비스  코드명
				If NOT itemNode.SelectSingleNode("svcCodeNm") is Nothing Then
					svcCodeNm = itemNode.SelectSingleNode("svcCodeNm").text
				End If
				'육성년도
				If NOT itemNode.SelectSingleNode("unbrngYear") is Nothing Then
					unbrngYear = itemNode.SelectSingleNode("unbrngYear").text
				End If
				'육성 기관 정보
				If NOT itemNode.SelectSingleNode("unbrngInsttInfo") is Nothing Then
					unbrngInsttInfo = itemNode.SelectSingleNode("unbrngInsttInfo").text
				End If
				'컨텐츠 제목
				If NOT itemNode.SelectSingleNode("cntntsSj") is Nothing Then
					cntntsSj = itemNode.SelectSingleNode("cntntsSj").text
				End If
				'주요 특성 정보
				If NOT itemNode.SelectSingleNode("mainChartrInfo") is Nothing Then
					mainChartrInfo = itemNode.SelectSingleNode("mainChartrInfo").text
				End If
				'파일 경로
				If NOT itemNode.SelectSingleNode("atchFileLink") is Nothing Then
					atchFileLink = itemNode.SelectSingleNode("atchFileLink").text
				End If
				'피일 명
				If NOT itemNode.SelectSingleNode("orginlFileNm") is Nothing Then
					orginlFileNm = itemNode.SelectSingleNode("orginlFileNm").text
				End If
				'이미지 경로
				If NOT itemNode.SelectSingleNode("imgFileLink") is Nothing Then
					imgFileLink = itemNode.SelectSingleNode("imgFileLink").text
				End If
			End If
%>
		<tr>
		    <td><img src="<%=imgFileLink%>" width="128" height="103"></img></td>
   			<td><%=svcCodeNm%></td>
   			<td><%=unbrngYear%></td>
   			<td><%=unbrngInsttInfo%></td>
   			<td><a href="<%=atchFileLink%>"><%=cntntsSj%></a></td>
   			<td><%=mainChartrInfo%></td>
		</tr>
<%
		   Set itemNode = Nothing
		Next
		Response.Write("</table><br>")
	End If
	
	'페이징 처리
	function ceil(x)

        dim temp
        temp = Round(x)
        if temp < x then
            temp = temp + 1
        end if
        ceil = temp
    end function


	pageGroupSize = 10
	pageSize = Int(numOfRowsText)


	start = Int(pageNoText)
	
	currentPage = Int(pageNoText)

	startRow = (currentPage - 1) * pageSize + 1
	endRow = currentPage * pageSize
	count = Int(totalCountText)
	number=0                                                    
		
	number=count-(currentPage-1)*pageSize    
	
	pageGroupCount = count/(pageSize*pageGroupSize)

	numPageGroup = Int(ceil(currentPage/pageGroupSize))

	If count > 0 Then
		pageCount = Int(count / pageSize)


		If (count Mod pageSize) = 0 Then
			pageCount = pageCount + 0
		Else
			pageCount = pageCount + 1
		End If

		startPage = pageGroupSize*(numPageGroup-1)+1
		endPage = startPage + pageGroupSize-1
		prtPageNo = 0
		
		If endPage > pageCount Then
			endPage = pageCount
		End If

		If numPageGroup > 1 Then
			prtPageNo = (numPageGroup-2)*pageGroupSize+1
			Response.Write("<a href='javascript:fncGoPage("&prtPageNo&");'>[이전]</a>")
		End If

		i=startPage
		While i<=endPage

			prtPageNo = i
			Response.Write("<a href='javascript:fncGoPage("&prtPageNo&");'>")

			If currentPage = i Then
				Response.Write("<strong>["&i&"]</strong>")
			Else
				Response.Write("["&i&"]")
			End If

			Response.Write("</a>")

			i = i+1
		Wend

		If numPageGroup < pageGroupCount Then
			prtPageNo = (numPageGroup*pageGroupSize+1)
			Response.Write("<a href='javascript:fncGoPage("&prtPageNo&");'>[다음]</a>")
		End If
	End If
	'페이징처리 끝
End If
%>
</body>
</html>