#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.httpadapter
~~~~~~~~~~~~~~~~~

This module provides a http adapter object to manage and persist 
http settings (headers, bodies). The adapter supports both
raw URL paths and RESTful route definitions, and integrates with
Request and Response objects to handle client-server communication.
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict
import base64
import asyncio
import inspect

class HttpAdapter:
    """
    A mutable :class:`HTTP adapter <HTTP adapter>` for managing client connections
    and routing requests.

    The `HttpAdapter` class encapsulates the logic for receiving HTTP requests,
    dispatching them to appropriate route handlers, and constructing responses.
    It supports RESTful routing via hooks and integrates with :class:`Request <Request>` 
    and :class:`Response <Response>` objects for full request lifecycle management.

    Attributes:
        ip (str): IP address of the client.
        port (int): Port number of the client.
        conn (socket): Active socket connection.
        connaddr (tuple): Address of the connected client.
        routes (dict): Mapping of route paths to handler functions.
        request (Request): Request object for parsing incoming data.
        response (Response): Response object for building and sending replies.
    """

    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        """
        Initialize a new HttpAdapter instance.

        :param ip (str): IP address of the client.
        :param port (int): Port number of the client.
        :param conn (socket): Active socket connection.
        :param connaddr (tuple): Address of the connected client.
        :param routes (dict): Mapping of route paths to handler functions.
        """

        #: IP address.
        self.ip = ip
        #: Port.
        self.port = port
        #: Connection
        self.conn = conn
        #: Conndection address
        self.connaddr = connaddr
        #: Routes
        self.routes = routes
        #: Request
        self.request = Request()
        #: Response
        self.response = Response()

    def handle_client(self, conn, addr, routes):

        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        try:
            msg = conn.recv(4096).decode("utf-8")
            print(f"[Debug] Request Body after prepare: {req.body}")
            if not msg:
                conn.close()
                return
            req.prepare(msg, self.routes)
            print("[HttpAdapter] Invoke handle_client connection {}".format(addr))

            # Lấy origin động
            origin = req.headers.get('origin', '*') if isinstance(req.headers, dict) else '*'

            # Xử lý CORS preflight
            if req.method == "OPTIONS":
                response = (
                    "HTTP/1.1 204 No Content\r\n"
                    "Access-Control-Allow-Origin: {}\r\n".format(origin) +
                    "Access-Control-Allow-Credentials: true\r\n"
                    "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: content-type, authorization, x-requested-with\r\n"
                    "Content-Length: 0\r\n"
                    "\r\n"
                ).encode()
                conn.sendall(response)
                conn.close()
                return

            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"

            if req.hook:
                try:
                    if inspect.iscoroutinefunction(req.hook):
                        result = asyncio.run(req.hook(req.headers, req.body))
                    else:
                        result = req.hook(req.headers, req.body)

                    if result:
                        cors_headers = (
                            "Access-Control-Allow-Origin: {}\r\n"
                            "Access-Control-Allow-Credentials: true\r\n"
                            "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
                            "Access-Control-Allow-Headers: content-type, authorization, x-requested-with\r\n"
                        ).format(origin)

                        if isinstance(result, bytes):
                            if result.startswith(b"HTTP/"):
                                response = result.replace(
                                    b"\r\n\r\n",
                                    ("\r\n" + cors_headers + "\r\n").encode(),
                                    1
                                )
                            else:
                                header_str = (
                                    "HTTP/1.1 200 OK\r\n"
                                    "Content-Type: application/json\r\n"
                                    + cors_headers +
                                    "Content-Length: {}\r\n"
                                    "\r\n"
                                ).format(len(result))
                                response = header_str.encode("utf-8") + result

                        elif isinstance(result, dict):
                            import json as _json
                            body = _json.dumps(result).encode("utf-8")
                            header_str = (
                                "HTTP/1.1 200 OK\r\n"
                                "Content-Type: application/json\r\n"
                                + cors_headers +
                                "Content-Length: {}\r\n"
                                "\r\n"
                            ).format(len(body))
                            response = header_str.encode("utf-8") + body

                        elif isinstance(result, str):
                            body = result.encode("utf-8")
                            header_str = (
                                "HTTP/1.1 200 OK\r\n"
                                "Content-Type: text/plain\r\n"
                                + cors_headers +
                                "Content-Length: {}\r\n"
                                "\r\n"
                            ).format(len(body))
                            response = header_str.encode("utf-8") + body

                except Exception as e:
                    print(f"[HttpAdapter] Hook Execution Error: {e}")
                    response = b"HTTP/1.1 500 Internal Server Error\r\n\r\n"
            else:
                try:
                    response = resp.build_response(req)
                except Exception as e:
                    print("[HttpAdapter] build_response Error: {}".format(e))
                    response = b"HTTP/1.1 500 Internal Server Error\r\n\r\n"
            
            print("[HttpAdapter] Response content {}".format(response[:100]))
            conn.sendall(response)
        except Exception as e:
            print(f"[HttpAdapter] Socket Error: {e}")
        finally:
            conn.close()

    async def handle_client_coroutine(self, reader, writer):
        """
        Handle an incoming client connection using stream reader writer asynchronously.

        This method reads the request from the socket, prepares the request object,
        invokes the appropriate route handler if available, builds the response,
        and sends it back to the client.

        :param conn (socket): The client socket connection.
        :param addr (tuple): The client's address.
        :param routes (dict): The route mapping for dispatching requests.
        """
        # Request handler
        req = self.request
        # Response handler
        resp = self.response

        print("[HttpAdapter] Invoke handle_client_coroutine connection {}".format(addr))
        addr = writer.get_extra_info("peername")

        # TODO Handle the request asynchronously
        msg = await reader.read(4096)
        if not msg:
            writer.close()
            await writer.wait_closed()
            return

        req.prepare(msg.decode("utf-8"), routes=self.routes)
        
        # Handle request hook
        if req.hook:
            #
            # TODO: handle for App hook here
            #
            try:
                if inspect.iscoroutinefunction(req.hook):
                    result = await req.hook(req.headers, req.body)
                else:
                    result = req.hook(req.headers, req.body)
                if result:
                    req.body = result if isinstance(result, bytes) else str(result).encode("utf-8")
            except Exception as e:
                print(f"[HttpAdapter] Async Hook Execution Error: {e}")
        # Build response
        print("[HttpAdapter] Start **ASYNC** build_response with type {}".format(type(req)))
        response = resp.build_response(req)
        print(f"[Debug] Response type: {type(response)}")
        print(f"[Debug] Raw response: {response[:50]}...")
        writer.write(response)
        await writer.drain()

    @property
    def extract_cookies(self, req, resp):
        """
        Build cookies from the :class:`Request <Request>` headers.

        :param req:(Request) The :class:`Request <Request>` object.
        :param resp: (Response) The res:class:`Response <Response>` object.
        :rtype: cookies - A dictionary of cookie key-value pairs.
        """
        cookies = {}
        for header in req.headers:
            if header.startswith("Cookie:"):
                cookie_str = header.split(":", 1)[1].strip()
                for pair in cookie_str.split(";"):
                    key, value = pair.strip().split("=")
                    cookies[key] = value
        return cookies

    def build_response(self, req, resp):
        """Builds a :class:`Response <Response>` object 

        :param req: The :class:`Request <Request>` used to generate the response.
        :param resp: The  response object.
        :rtype: Response
        """
        response = Response()

        # Set encoding.
        response.encoding = get_encoding_from_headers(response.headers)
        response.raw = resp
        response.reason = response.raw.reason

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        # Add new cookies from the server.
        response.cookies = extract_cookies(req)

        # Give the Response some context.
        response.request = req
        response.connection = self

        return response

    def build_json_response(self, req, resp):
        """Builds a :class:`Response <Response>` object from JSON data

        :param req: The :class:`Request <Request>` used to generate the response.
        :param resp: The  response object.
        :rtype: Response
        """
        response = Response(req)

        # Set encoding.
        response.raw = resp

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        # Give the Response some context.
        response.request = req
        response.connection = self

        return response


    # def get_connection(self, url, proxies=None):
        # """Returns a url connection for the given URL. 

        # :param url: The URL to connect to.
        # :param proxies: (optional) A Requests-style dictionary of proxies used on this request.
        # :rtype: int
        # """

        # proxy = select_proxy(url, proxies)

        # if proxy:
            # proxy = prepend_scheme_if_needed(proxy, "http")
            # proxy_url = parse_url(proxy)
            # if not proxy_url.host:
                # raise InvalidProxyURL(
                    # "Please check proxy URL. It is malformed "
                    # "and could be missing the host."
                # )
            # proxy_manager = self.proxy_manager_for(proxy)
            # conn = proxy_manager.connection_from_url(url)
        # else:
            # # Only scheme should be lower case
            # parsed = urlparse(url)
            # url = parsed.geturl()
            # conn = self.poolmanager.connection_from_url(url)

        # return conn


    def add_headers(self, request):
        """
        Add headers to the request.

        This method is intended to be overridden by subclasses to inject
        custom headers. It does nothing by default.

        
        :param request: :class:`Request <Request>` to add headers to.
        """
        pass

    def build_proxy_headers(self, proxy):
        """Returns a dictionary of the headers to add to any request sent
        through a proxy. 

        :class:`HttpAdapter <HttpAdapter>`.

        :param proxy: The url of the proxy being used for this request.
        :rtype: dict
        """
        headers = {}
        #
        # TODO: build your authentication here
        #       username, password =...
        # we provide dummy auth here
        #
        username, password = ("user1", "password")

        if username and password:
            auth_str = f"{username}:{password}"
            auth_bytes = auth_str.encode('ascii')
            base64_auth = base64.b64encode(auth_bytes).decode('ascii')
            headers["Proxy-Authorization"] = f"Basic {base64_auth}"
        return headers