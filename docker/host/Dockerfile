FROM alpine:3.20

# Install networking diagnostic and testing tools
RUN apk update && \
    apk add --no-cache \
        bash \
        iproute2 \
        iputils \
        curl \
        iperf3 \
        tcpdump \
        bind-tools \
        ca-certificates && \
    rm -rf /var/cache/apk/*

CMD ["sh", "-c", "trap : TERM INT; sleep infinity & wait"]
