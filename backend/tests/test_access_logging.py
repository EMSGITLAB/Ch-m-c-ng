import logging

from app.access_logging import NoQueryString


def test_do_not_log_employee_search_terms_or_query_tokens():
    record=logging.LogRecord("uvicorn.access",logging.INFO,"",1,'%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1","GET","/api/admin/employees?q=personal-name&token=secret","1.1",200),None)
    assert NoQueryString().filter(record)
    assert record.args[2]=="/api/admin/employees"
    assert "personal-name" not in record.getMessage()
    assert "secret" not in record.getMessage()
