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
<title>농작업일정</title>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<%
String sj = request.getParameter("sj");
String listCategoryNm = request.getParameter("listCategoryNm");
%>

<h3><strong>농작업일정(<%=listCategoryNm%>-<%=sj%>)</strong></h3>
<hr>

<%
//농작업일정 상세조회
if(request.getParameter("cntntsNo")!=null && !request.getParameter("cntntsNo").equals("")){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	String apiKey="발급받은인증키를삽입하세요";
	//서비스 명
	String serviceName="farmWorkingPlanNew";
	//오퍼레이션 명
	String operationName="workScheduleEraInfoLst";

	//XML 받을 URL 생성
	String parameter = "/"+serviceName+"/"+operationName;
	parameter += "?apiKey="+ apiKey;
	parameter += "&cntntsNo="+ request.getParameter("cntntsNo");

	//서버와 통신
	URL apiUrl = new URL("http://api.nongsaro.go.kr/service"+parameter);
	InputStream apiStream = apiUrl.openStream();

	Document doc = null;
	try{
		//xml document
		doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(apiStream);
	}catch(Exception e){
		e.printStackTrace();
	}finally{
		apiStream.close();
	}

	int size = 0;

	NodeList items = null;
	NodeList htmlCns = null;

	items = doc.getElementsByTagName("item");
	size = doc.getElementsByTagName("item").getLength();
	htmlCns = doc.getElementsByTagName("htmlCn");

	if(size==0){
%>
	<h3>조회한 정보가 없습니다.</h3>
<%
	}else{
%>
	<div>
<%
		for(int i=0; i<1; i++){
			//농작업 일정 정보
			String htmlCn = htmlCns.item(i).getFirstChild() == null ? "" : htmlCns.item(i).getFirstChild().getNodeValue();
%>
			<%=htmlCn%>
<%
		}
%>
	</div>
<%
	}

		//오퍼레이션 명
		operationName="workScheduleDtl";

		//XML 받을 URL 생성
		parameter = "/"+serviceName+"/"+operationName;
		parameter += "?apiKey="+ apiKey;
		parameter += "&cntntsNo="+ request.getParameter("cntntsNo");

		//서버와 통신
		apiUrl = new URL("http://api.nongsaro.go.kr/service"+parameter);
		apiStream = apiUrl.openStream();

		doc = null;
		try{
			//xml document
			doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(apiStream);
		}catch(Exception e){
			e.printStackTrace();
		}finally{
			apiStream.close();
		}

		//내용
		String cn = null;

		try{cn = doc.getElementsByTagName("cn").item(0).getFirstChild().getNodeValue();}catch(Exception e){cn = "";}
		cn = cn.replaceAll("<table", "<table border=\"1\" cellspacing=\"0\" cellpadding=\"0\"");
	%>
		<div>
			<%=cn%>
		</div>
	<%
}
%>
<br>
<input type="button" onclick="javascript:location.href='farmWorkingPlan.jsp'" value="처음화면으로"/>&nbsp;
</body>
</html>