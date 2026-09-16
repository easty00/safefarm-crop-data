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
<title>병해충 발생정보</title>
<script type="text/javascript">

//검색
function fncSearch(){
	with(document.searchApiForm){
		method="get";
		action = "dbyhsCccrrncInfo.jsp";
		target = "_self";
		submit();
	}
}

//페이지 이동
function fncGoPage(page){
	with(document.searchApiForm){
		pageNo.value = page;
		method="get";
		action = "dbyhsCccrrncInfo.jsp";
		target = "_self";
		submit();
	}
}

</script>
</head>
<body>
<h4><strong> * 샘플화면은 디자인을 적용하지 않았으니, 개별 사이트의 스타일에 맞게 코딩하시기 바랍니다.</strong></h4>
<h3><strong>병해충 발생정보</strong></h3><hr>

<form name="searchApiForm">
<input type="hidden" name="pageNo">
<select name="sYear"> 
<%
//병해충 발생정보 연도 콤보
if(true){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	String apiKey="nongsaroSampleKey"; 
	//서비스 명
	String serviceName="dbyhsCccrrncInfo";
	//오퍼레이션 명
	String operationName="dbyhsCccrrncInfoYear";

	//XML 받을 URL 생성
	String parameter = "/"+serviceName+"/"+operationName;
	parameter += "?apiKey="+ apiKey;
	
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
	NodeList yearCnts = null;
	NodeList yearCodes = null;
	
	items = doc.getElementsByTagName("item");
	size = doc.getElementsByTagName("item").getLength();
	yearCnts = doc.getElementsByTagName("yearCnt");
	yearCodes = doc.getElementsByTagName("yearCode");

	for(int i=0; i<size; i++){
		//년도 카운트
		String yearCnt = yearCnts.item(i).getFirstChild() == null ? "" : yearCnts.item(i).getFirstChild().getNodeValue();
		//년도 명
		String yearCode = yearCodes.item(i).getFirstChild() == null ? "" : yearCodes.item(i).getFirstChild().getNodeValue();
%>
		<option value="<%=yearCode%>" <%=request.getParameter("sYear")!=null && request.getParameter("sYear").equals(yearCode)?"selected":""%>><%=yearCode%>(<%=yearCnt%>)</option>
<%		
	}
}
%>
</select>
<select name="sType"> 
	<option value="sCntntsSj" <%=request.getParameter("sType")!=null && request.getParameter("sType").equals("sCntntsSj")?"selected":""%>>제목</option>
	<option value="sWriteNm" <%=request.getParameter("sType")!=null && request.getParameter("sType").equals("sWriteNm")?"selected":""%>>작성자</option>
</select>
<input type="Text" name="sText" value="<%=request.getParameter("sText")==null?"":request.getParameter("sText")%>">
<input type="button" name="search" value="검색" onclick="return fncSearch();"/>
</form>

<form name="pageApiForm">
<input type="hidden" name="pageNo">
</form>

<%
//병해충 발생정보 리스트
if(true){
	//apiKey - 농사로 Open API에서 신청 후 승인되면 확인 가능
	String apiKey="nongsaroSampleKey"; 
	//서비스 명
	String serviceName="dbyhsCccrrncInfo";
	//오퍼레이션 명
	String operationName="dbyhsCccrrncInfoList";
	
	//XML 받을 URL 생성
	String parameter = "/"+serviceName+"/"+operationName;
	parameter += "?apiKey="+ apiKey;
	parameter += "&pageNo="+request.getParameter("pageNo");
	
	//년도 검색
	if(request.getParameter("sYear")!=null&&!request.getParameter("sYear").equals("")){
		if(request.getParameter("sYear").equals("전체")){
			parameter += "&sYear=";
		}else{
			parameter += "&sYear="+request.getParameter("sYear");
		}
	}
	//검색 조건
	if(request.getParameter("sType")!=null&&!request.getParameter("sType").equals("")){
		parameter += "&sType="+ request.getParameter("sType");
	}
	//검색어
	if(request.getParameter("sText")!=null&&!request.getParameter("sText").equals("")){
		parameter += "&sText="+ request.getParameter("sText");
	}
	
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
	NodeList cntntsSjs = null; 
	NodeList updusrEsntlNms = null;
	NodeList registDts = null;
	NodeList cntntsRdcnts = null;
	NodeList downFiles = null;
	NodeList rtnOrginlFileNms = null;
	NodeList cntntsNos = null;
	
	items = doc.getElementsByTagName("item");
	size = doc.getElementsByTagName("item").getLength();
	cntntsSjs = doc.getElementsByTagName("cntntsSj");
	updusrEsntlNms = doc.getElementsByTagName("updusrEsntlNm");
	registDts = doc.getElementsByTagName("registDt");
	cntntsRdcnts = doc.getElementsByTagName("cntntsRdcnt");
	downFiles = doc.getElementsByTagName("downFile");
	rtnOrginlFileNms = doc.getElementsByTagName("rtnOrginlFileNm");
	cntntsNos = doc.getElementsByTagName("cntntsNo");

	if(size==0){ %>
	<h3>조회한 정보가 없습니다.</h3>
<%	}else{ %>
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
<%
		for(int i=0; i<size; i++){
			//컨텐츠 제목
			String cntntsSj = cntntsSjs.item(i).getFirstChild() == null ? "" : cntntsSjs.item(i).getFirstChild().getNodeValue();
			//등록자
			String updusrEsntlNm = updusrEsntlNms.item(i).getFirstChild() == null ? "" : updusrEsntlNms.item(i).getFirstChild().getNodeValue(); 
			//등록 일자
			String registDt = registDts.item(i).getFirstChild() == null ? "" : registDts.item(i).getFirstChild().getNodeValue();
			//조회수
			String cntntsRdcnt = cntntsRdcnts.item(i).getFirstChild() == null ? "" : cntntsRdcnts.item(i).getFirstChild().getNodeValue();
			//파일경로
			String downFile = downFiles.item(i).getFirstChild() == null ? "" : downFiles.item(i).getFirstChild().getNodeValue();
			//파일명
			String rtnOrginlFileNm = rtnOrginlFileNms.item(i).getFirstChild() == null ? "" : rtnOrginlFileNms.item(i).getFirstChild().getNodeValue();
			//컨텐츠 번호
			String cntntsNo = cntntsNos.item(i).getFirstChild() == null ? "" : cntntsNos.item(i).getFirstChild().getNodeValue();
			
%>
		<tr>
			<td><%=cntntsSj%></td>
			<td align="center"><%=updusrEsntlNm%></td>
			<td align="center"><%=registDt%></td>
			<td align="center"><%=cntntsRdcnt%></td>
			<td align="center"><a href="<%=downFile%>">파일 다운로드</a></td>
		</tr>
<%		
		}
%>
	</table>
<%
	}
//페이징 처리
	//한 페이지에 제공할 건수
	String numOfRows = "";
	//조회된 총 건수
	String totalCount = "";
	//조회라 페이지 번호
	String pageNo = "";
	try{numOfRows = doc.getElementsByTagName("numOfRows").item(0).getFirstChild().getNodeValue();}catch(Exception e){numOfRows = "";}
	try{totalCount = doc.getElementsByTagName("totalCount").item(0).getFirstChild().getNodeValue();}catch(Exception e){totalCount = "";}
	try{pageNo = doc.getElementsByTagName("pageNo").item(0).getFirstChild().getNodeValue();}catch(Exception e){pageNo = "";}

	int pageGroupSize = 10;
	int pageSize = 0;
	try{
		pageSize = Integer.parseInt(numOfRows);
	}catch(Exception e){
		pageSize = 10;
	}
	int start = 0; 
	try{
		start = Integer.parseInt(pageNo);
	}catch(Exception e){
		start = 1;
	}
	
	
	int currentPage = 1;
	try{currentPage = Integer.parseInt(pageNo);}catch(Exception e){}

	int startRow = (currentPage - 1) * pageSize + 1;//한 페이지의 시작글 번호 
	int endRow = currentPage * pageSize;//한 페이지의 마지막 글번호           
	int count = Integer.parseInt( totalCount);                                                            
	int number=0;                                                             

		
	number=count-(currentPage-1)*pageSize;//글목록에 표시할 글번호                                                                  
    
	//페이지그룹의 갯수                                                                                                             
	//ex) pageGroupSize가 3일 경우 '[1][2][3]'가 pageGroupCount 개 만큼 있다.                                                       
	int pageGroupCount = count/(pageSize*pageGroupSize)+( count % (pageSize*pageGroupSize) == 0 ? 0 : 1);                           
	//페이지 그룹 번호                                                                                                              
	//ex) pageGroupSize가 3일 경우  '[1][2][3]'의 페이지그룹번호는 1 이고  '[2][3][4]'의 페이지그룹번호는 2 이다.                   
	int numPageGroup = (int) Math.ceil((double)currentPage/pageGroupSize);                                                          


	if(count > 0){
		int pageCount = count / pageSize + ( count % pageSize == 0 ? 0 : 1);
		int startPage = pageGroupSize*(numPageGroup-1)+1;
		int endPage = startPage + pageGroupSize-1;
		int prtPageNo = 0;
		
		if(endPage > pageCount){
			endPage = pageCount;
		}
		
		if(numPageGroup > 1){
			prtPageNo = (numPageGroup-2)*pageGroupSize+1;
			out.println("<a href='javascript:fncGoPage("+prtPageNo+");'>[이전]</a>");
		}
		
		for(int i=startPage; i<=endPage; i++){
			prtPageNo = i;
			out.print("<a href='javascript:fncGoPage("+prtPageNo+");'>");
			if(currentPage == i){
				out.print("<strong>["+i+"]</strong>");
			}else{
				out.print("["+i+"]");
			}
			out.println("</a>");
		}
		
		if(numPageGroup < pageGroupCount){
			prtPageNo = (numPageGroup*pageGroupSize+1);
			out.println("<a href='javascript:fncGoPage("+prtPageNo+");'>[다음]</a>");
		}
	}
	//페이징 처리 끝
}
%>
</body>
</html>