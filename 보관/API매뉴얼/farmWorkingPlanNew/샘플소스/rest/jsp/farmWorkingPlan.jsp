<%@page import="java.io.InputStream"%>
<%@page import="java.net.URLEncoder"%>
<%@page import="org.w3c.dom.NodeList"%>
<%@page import="org.w3c.dom.Node"%>
<%@page import="org.w3c.dom.Element"%>
<%@page import="javax.xml.parsers.DocumentBuilderFactory"%>
<%@page import="org.w3c.dom.Document"%>
<%@page import="java.net.URL"%>

<%@ page language="java" contentType="text/html; charset=UTF-8"
    pageEncoding="UTF-8"%>
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<title>농작업 일정</title>
<script type="text/javascript">

//세부항목 리스트 이동
function fncNextList(kCode, cNm){
	with(document.listApiForm){
		listCategoryCode.value = kCode;
		listCategoryNm.value = cNm;
		method="get";
		action = "farmWorkingPlan.jsp";
		target = "_self";
		submit();
	}
}

function move(dNo,nm){
	with(document.listApiForm){
		cntntsNo.value = dNo;
		sj.value = nm;
		method="get";
		action = "farmWorkingPlan_D.jsp";
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
	<input type="hidden" name="listCategoryCode" value="<%=request.getParameter("listCategoryCode") %>">
	<input type="hidden" name="listCategoryNm" value="<%=request.getParameter("listCategoryNm") %>">
	<input type="hidden" name="cntntsNo" >
	<input type="hidden" name="sj" >
</form>

<!-- =================================================== 메인 카테고리 시작 ================================================================================ -->

<%
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	String apiKey="발급받은인증키를삽입하세요";
	//서비스 명
	String serviceName="farmWorkingPlanNew";
	//오퍼레이션 명
	String operationName="workScheduleGrpList";

	//XML 받을 URL 생성
	String parameter = "/"+serviceName+"/"+operationName;
	parameter += "?apiKey="+ apiKey;

	//메인카테고리 서버와 통신
	URL apiUrl = new URL("http://api.nongsaro.go.kr/service"+parameter);
	InputStream apiStream = apiUrl.openStream();

	Document mainDoc = null;
	try{
		//xml document
		mainDoc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(apiStream);
	}catch(Exception e){
		e.printStackTrace();
	}finally{
		apiStream.close();
	}

	int size = 0;

	NodeList items = null;
	NodeList codeNms = null;
	NodeList kidofcomdtySeCodes = null;
	NodeList sorts = null;

	items = mainDoc.getElementsByTagName("item");
	size = mainDoc.getElementsByTagName("item").getLength();
	codeNms = mainDoc.getElementsByTagName("codeNm");
	kidofcomdtySeCodes = mainDoc.getElementsByTagName("kidofcomdtySeCode");
	sorts = mainDoc.getElementsByTagName("sort");

	if(size==0){
%>
	<h3>조회한 정보가 없습니다.</h3>
<%
	}else{
%>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
		<tr>
<%
		for(int i=0; i<size; i++){
			//농작업 일정 항목명
			String codeNm = codeNms.item(i).getFirstChild() == null ? "" : codeNms.item(i).getFirstChild().getNodeValue();
			//일정 코드
			String kidofcomdtySeCode = kidofcomdtySeCodes.item(i).getFirstChild() == null ? "" : kidofcomdtySeCodes.item(i).getFirstChild().getNodeValue();
%>
			<td width="10%" align="center"><a href="javascript:fncNextList('<%=kidofcomdtySeCode%>','<%=codeNm%>');"><%=codeNm%></a></td>
<%
		}
%>
		<tr>
	</table>
<%
	}
%>

<!-- =================================================== 메인 카테고리 끝 ================================================================================ -->

<!-- =================================================== 세부항목 리스트 시작 ================================================================================ -->

<%
//일정별 리스트
if(request.getParameter("listCategoryCode")!=null && !request.getParameter("listCategoryCode").equals("")){
	//오퍼레이션 명
	operationName="workScheduleLst";

	parameter = "/"+serviceName+"/"+operationName;
	parameter += "?apiKey="+ apiKey;
	parameter += "&kidofcomdtySeCode="+request.getParameter("listCategoryCode");

	//리스트 서버와 통신
	URL listApiUrl = new URL("http://api.nongsaro.go.kr/service"+parameter);
	InputStream listApiStream = listApiUrl.openStream();

	Document listDoc = null;
	try{
		//xml document
		listDoc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(listApiStream);
	}catch(Exception e){
		e.printStackTrace();
	}finally{
		listApiStream.close();
	}

	int listSize = 0;

	NodeList listItems = null;
	NodeList cntntsNos = null;
	NodeList fileDownUrlInfos = null;
	NodeList fileSeCodes = null;
	NodeList orginlFileNms = null;
	NodeList sjs = null;

	listItems = listDoc.getElementsByTagName("item");
	listSize = listDoc.getElementsByTagName("item").getLength();
	cntntsNos = listDoc.getElementsByTagName("cntntsNo");
	fileDownUrlInfos = listDoc.getElementsByTagName("fileDownUrlInfo");
	fileSeCodes = listDoc.getElementsByTagName("fileSeCode");
	orginlFileNms = listDoc.getElementsByTagName("orginlFileNm");
	sjs = listDoc.getElementsByTagName("sj");

	if(listSize==0){
%>
	<h3>조회한 정보가 없습니다.</h3>
<%
	}else{
%>
	<table width="100%" border="1" cellSpacing="0" cellPadding="0">
<%
		for(int i=0; i<listSize; i++){
			//키값
			String cntntsNo = cntntsNos.item(i).getFirstChild() == null ? "" : cntntsNos.item(i).getFirstChild().getNodeValue();
			//파일 링크
			String fileDownUrlInfo = fileDownUrlInfos.item(i).getFirstChild() == null ? "" : fileDownUrlInfos.item(i).getFirstChild().getNodeValue();
			//파일 원본 이름
			String orginlFileNm = orginlFileNms.item(i).getFirstChild() == null ? "" : orginlFileNms.item(i).getFirstChild().getNodeValue();
			//확장자명을 제외한 파일 이름
			String sj = sjs.item(i).getFirstChild() == null ? "" : sjs.item(i).getFirstChild().getNodeValue();
%>
		<tr>
		    <td width="50%"><a href="javascript:;move('<%=cntntsNo%>','<%=sj%>');"><%=sj%></a></td>
		    <td width="50%"><a href="<%=fileDownUrlInfo %>">파일다운로드</a></td>
		</tr>
<%
		}
%>
	</table>
<%
	}
}
%>
<!-- =================================================== 세부항목 리스트 끝 ================================================================================ -->
</body>
</html>