import logging


class NoQueryString(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)==5 and isinstance(record.args[2],str):
            args=list(record.args)
            args[2]=args[2].split("?",1)[0]
            record.args=tuple(args)
        return True


def configure_access_logging():
    logger=logging.getLogger("uvicorn.access")
    if not any(isinstance(filter_,NoQueryString) for filter_ in logger.filters):
        logger.addFilter(NoQueryString())
