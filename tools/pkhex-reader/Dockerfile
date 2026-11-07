FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src

RUN git clone https://github.com/kwsch/PKHeX.git PKHeX \
    && git -C PKHeX checkout 0660d1e1f4924b8478daec73281bb8071a82ad19

WORKDIR /src/PKHeXReader
COPY PKHeXReader.csproj .
COPY Program.cs .
RUN dotnet publish PKHeXReader.csproj -c Release -o /out

FROM mcr.microsoft.com/dotnet/runtime:10.0
WORKDIR /app
COPY --from=build /out .
ENTRYPOINT ["dotnet", "PKHeXReader.dll"]
