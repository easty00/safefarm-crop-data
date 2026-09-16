<% @CODEPAGE="65001" language="VBScript" %>
<html>
<head>
<meta http-dquiv="Content-Type" content="text/html" charset="utf-8">
<title>농작업일정</title>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>농작업일정</strong></h3>
<hr>

<%
'농작업일정 상세 조회
If Not Request("cntntsNo") Is Nothing And Request("cntntsNo") <> "" Then

	'apiKey - 농사로 Open API에서 신청 후 승인되면 확인가능
	apiKey = "발급받은인증키를삽입하세요"
	'서비스 명
	serviceName = "farmWorkingPlanNew"
	'오퍼레이션 명
	operationName = "workScheduleEraInfoLst"

	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey=" & apiKey
	parameter = parameter & "&cntntsNo=" & Request("cntntsNo")


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

	If cnt = 0 Then
		Response.Write("<h3>조회한 정보가 없습니다.</h3>")
	Else
%>
	<hr>
	<div>
<%
		For i=0 To 0
		   Set itemNode = items.item(i)
			If NOT itemNode Is Nothing Then
				'내용
				If NOT itemNode.SelectSingleNode("htmlCn") is Nothing Then
					htmlCn = itemNode.SelectSingleNode("htmlCn").text
				End If
			End If
%>
			<%=htmlCn%>

<%
		   Set itemNode = Nothing
		Next
		Response.Write("</div>")
	End If




	'apiKey - 농사로 Open API에서 신청 후 승인되면 확인가능
	apiKey = "발급받은인증키를삽입하세요"
	'서비스 명
	serviceName = "farmWorkingPlanNew"
	'오퍼레이션 명
	operationName = "workScheduleDtl"

	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey="&apiKey
	parameter = parameter & "&cntntsNo=" & Request("cntntsNo")

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

	Set item = xmlDOM.SelectNodes("//body")
	cnt = item(0).childNodes.length

	If cnt = 0 Then
		Response.Write("<h3>조회한 정보가 없습니다.</h3>")
	Else
		'내용
		Set cn = xmlDOM.SelectNodes("//cn")
		If Not cn(0) Is Nothing Then cnText= cn(0).Text Else cnText = "" End If

%>
		<div>
			<%=Replace(cnText,"<table","<table border='1' cellspacing='0' cellpadding='0'")%>
		</div>
<%
	End If
End If
%>
<input type="button" onclick="javascript:location.href='farmWorkingPlan.asp'" value="처음화면으로"/>&nbsp;
</body>
</html>