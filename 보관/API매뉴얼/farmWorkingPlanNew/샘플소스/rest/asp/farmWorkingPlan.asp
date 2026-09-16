<% @CODEPAGE="65001" language="VBScript" %>
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
		action = "farmWorkingPlan.asp";
		target = "_self";
		submit();
	}
}

function move(dNo,nm){
	with(document.listApiForm){
		cntntsNo.value = dNo;
		sj.value = nm;
		method="get";
		action = "farmWorkingPlan_D.asp";
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
	<input type="hidden" name="listCategoryCode" value="<%=Request("listCategoryCode") %>">
	<input type="hidden" name="listCategoryNm" value="<%=Request("listCategoryNm") %>">
	<input type="hidden" name="cntntsNo" >
	<input type="hidden" name="sj" >
</form>

<%
'일정 리스트
If true Then
	'apiKey - 농사로 Open API에서 신청 후 승인되면 확인가능
	apiKey = "발급받은인증키를삽입하세요"
	'서비스 명
	serviceName = "farmWorkingPlanNew"
	'오퍼레이션 명
	operationName = "workScheduleGrpList"

	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey="&apiKey

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
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<tr>
<%
		For i=0 To cnt-1
		   Set itemNode = items.item(i)
			If NOT itemNode Is Nothing Then
				If NOT itemNode.SelectSingleNode("codeNm") is Nothing Then
					codeNm = itemNode.SelectSingleNode("codeNm").text
				End If
				If NOT itemNode.SelectSingleNode("kidofcomdtySeCode") is Nothing Then
					kidofcomdtySeCode = itemNode.SelectSingleNode("kidofcomdtySeCode").text
				End If
			End If
%>
			<td width="10%" align="center"><a href="javascript:fncNextList('<%=kidofcomdtySeCode %>','<%=codeNm %>');"><%=codeNm %></a></td>
<%
		   Set itemNode = Nothing
		Next
		Response.Write("</tr></table>")
	End If
End If
%>

<%
'일정별 리스트
If Not Request("listCategoryCode") Is Nothing And Request("listCategoryCode") <> "" Then
	'apiKey - 농사로 Open API에서 신청 후 승인되면 확인가능
	apiKey = "발급받은인증키를삽입하세요"
	'서비스 명
	serviceName = "farmWorkingPlanNew"
	'오퍼레이션 명
	operationName = "workScheduleLst"

	'XML 받을 URL 생성
	parameter = "/" & serviceName & "/" & operationName
	parameter = parameter & "?apiKey="&apiKey
	parameter = parameter & "&kidofcomdtySeCode="&Request("listCategoryCode")

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

%>
<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<%If cnt=0 Then %>
			<h3>조회한 정보가 없습니다.</h3>
        <%Else
		For i=0 To cnt-1
		   Set itemNode = items.item(i)
			If NOT itemNode Is Nothing Then
				'파일 링크
				If NOT itemNode.SelectSingleNode("fileDownUrlInfo") is Nothing Then
					fileDownUrlInfo = itemNode.SelectSingleNode("fileDownUrlInfo").text
				End If
				'파일 이름
				If NOT itemNode.SelectSingleNode("sj") is Nothing Then
					sj = itemNode.SelectSingleNode("sj").text
				End If
				'확장자명을 제외한 파일 이름
				If NOT itemNode.SelectSingleNode("orginlFileNm") is Nothing Then
					orginlFileNm = itemNode.SelectSingleNode("orginlFileNm").text
				End If
				'키값
				If NOT itemNode.SelectSingleNode("cntntsNo") is Nothing Then
					cntntsNo = itemNode.SelectSingleNode("cntntsNo").text
				End If
			End If
%>
		<tr>
		    <td width="50%"><a href="javascript:;move('<%=cntntsNo%>','<%=sj%>');"><%=sj%></a></td>
		    <td width="50%"><a href="<%=fileDownUrlInfo %>">파일다운로드</a></td>
		</tr>
<%
		   Set itemNode = Nothing
		Next
		Response.Write("</table>")
	End If
End If
%>
</body>
</html>