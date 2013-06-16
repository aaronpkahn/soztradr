function deleteSoz(key) {
	$('#mysozform').attr('action', '/delete?id='+key).submit();
	return false;
}

function acceptSoz(key) {
	$('#mysozform').attr('action', '/accept?id='+key).submit();
	return false;
}

function rejectSoz(key) {
	$('#mysozform').attr('action', '/reject?id='+key).submit();
	return false;
}