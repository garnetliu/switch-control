using System.Collections;
using System.Reflection;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using PKHeX.Core;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = 64 * 1024 * 1024);
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.MaxDepth = 64);
var app = builder.Build();

var scriptOptions = ScriptOptions.Default
    .AddReferences(
        typeof(PK8).Assembly,
        typeof(PkhexGlobals).Assembly,
        typeof(JsonElement).Assembly,
        typeof(Enumerable).Assembly)
    .AddImports(
        "System",
        "System.Linq",
        "System.Collections.Generic",
        "PKHeX.Core");

app.MapGet("/health", () => Results.Json(new
{
    status = "ok",
    service = "PKHeX.Core API",
    coreAssembly = typeof(PK8).Assembly.GetName().Version?.ToString(),
}));

app.MapGet("/api/v1/capabilities", () => Results.Json(new
{
    execution = "C# scripts run against PKHeX.Core in this container",
    imports = new[] { "System", "System.Linq", "System.Collections.Generic", "PKHeX.Core" },
    globals = new[] { "Input: JsonElement", "Data: byte[]", "AsPK8(): PK8" },
    endpoint = "POST /api/v1/execute",
    maxRequestBytes = 64 * 1024 * 1024,
}));

app.MapPost("/api/v1/execute", async (ExecuteRequest request, HttpContext context) =>
{
    if (string.IsNullOrWhiteSpace(request.Code))
        return Results.BadRequest(new { error = "code is required" });

    byte[] data;
    try
    {
        data = request.DataBase64 is not null
            ? Convert.FromBase64String(request.DataBase64)
            : request.DataHex is not null
                ? Convert.FromHexString(request.DataHex)
                : [];
    }
    catch (FormatException ex)
    {
        return Results.BadRequest(new { error = "invalid_data_encoding", detail = ex.Message });
    }

    var globals = new PkhexGlobals(request.Input ?? default, data);
    var script = CSharpScript.Create<object?>(request.Code, scriptOptions, typeof(PkhexGlobals));
    var diagnostics = script.Compile();
    var errors = diagnostics
        .Where(diagnostic => diagnostic.Severity == DiagnosticSeverity.Error)
        .Select(diagnostic => new { message = diagnostic.GetMessage(), line = diagnostic.Location.GetLineSpan().StartLinePosition.Line + 1 })
        .ToArray();
    if (errors.Length != 0)
        return Results.BadRequest(new { error = "compilation_failed", diagnostics = errors });

    try
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var state = await script.RunAsync(globals, cancellationToken: timeout.Token);
        return Results.Json(new
        {
            result = JsonValue.Normalize(state.ReturnValue),
            returnType = state.ReturnValue?.GetType().FullName,
        });
    }
    catch (OperationCanceledException)
    {
        return Results.Json(new { error = "execution_timeout", timeoutSeconds = 60 }, statusCode: 408);
    }
    catch (Exception ex)
    {
        return Results.BadRequest(new { error = "execution_failed", type = ex.GetType().FullName, detail = ex.Message });
    }
});

app.Run();

public sealed record ExecuteRequest(string Code, string? DataHex, string? DataBase64, JsonElement? Input);

public sealed class PkhexGlobals(JsonElement input, byte[] data)
{
    public JsonElement Input { get; } = input;
    public byte[] Data { get; } = data;
    public PK8 AsPK8() => new(Data);
}

public static class JsonValue
{
    public static object? Normalize(object? value, int depth = 0, HashSet<object>? seen = null)
    {
        if (value is null || value is string || value is bool || value is char || value is byte || value is sbyte ||
            value is short || value is ushort || value is int || value is uint || value is long || value is ulong ||
            value is float || value is double || value is decimal || value is DateTime || value is DateTimeOffset ||
            value is Guid || value is JsonElement)
            return value;
        if (value is byte[] bytes)
            return Convert.ToBase64String(bytes);
        if (value.GetType().IsEnum)
            return value.ToString();
        if (depth >= 5)
            return new { type = value.GetType().FullName };

        seen ??= new HashSet<object>(ReferenceEqualityComparer.Instance);
        if (!value.GetType().IsValueType && !seen.Add(value))
            return new { reference = value.GetType().FullName };

        if (value is IEnumerable sequence)
        {
            var list = new List<object?>();
            foreach (var item in sequence)
            {
                if (list.Count >= 1000)
                    break;
                list.Add(Normalize(item, depth + 1, seen));
            }
            return list;
        }

        var result = new Dictionary<string, object?>();
        foreach (var property in value.GetType().GetProperties(BindingFlags.Instance | BindingFlags.Public))
        {
            if (!property.CanRead || property.GetIndexParameters().Length != 0 || property.Name == "EqualityContract")
                continue;
            try
            {
                result[property.Name] = Normalize(property.GetValue(value), depth + 1, seen);
            }
            catch
            {
                result[property.Name] = null;
            }
        }
        return result.Count == 0 ? value.ToString() : result;
    }
}
