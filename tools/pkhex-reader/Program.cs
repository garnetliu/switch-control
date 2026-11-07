using System.Text.Json;
using PKHeX.Core;

const int PK8Size = 0x158;

if (args.Length != 1)
{
    Console.Error.WriteLine("Usage: PKHeXReader <memtest.json>");
    return 2;
}

using var document = JsonDocument.Parse(File.ReadAllText(args[0]));
var parsedCount = 0;
var rows = new List<object>();

foreach (var item in document.RootElement.EnumerateArray())
{
    if (!item.TryGetProperty("event", out var eventValue) || eventValue.GetString() is not ("starter-sample" or "lair-sample"))
        continue;
    if (!item.TryGetProperty("slots", out var slots))
        continue;

    var sample = item.TryGetProperty("sample", out var sampleValue) ? sampleValue.GetInt32() : (int?)null;
    var stage = item.TryGetProperty("stage", out var stageValue) ? stageValue.GetString() : null;

    foreach (var slot in slots.EnumerateObject())
    {
        if (!slot.Value.TryGetProperty("raw", out var rawValue))
            continue;

        var raw = rawValue.GetString() ?? "";
        var address = slot.Value.TryGetProperty("address", out var addressValue) ? addressValue.GetString() : null;
        byte[] data;
        try
        {
            data = Convert.FromHexString(raw);
        }
        catch (FormatException)
        {
            rows.Add(new { sample, stage, slot = slot.Name, address, bytes = raw.Length / 2, error = "invalid_hex" });
            continue;
        }

        if (data.Length != PK8Size)
        {
            rows.Add(new { sample, stage, slot = slot.Name, address, bytes = data.Length, error = "wrong_size", expectedBytes = PK8Size });
            continue;
        }

        try
        {
            var pk = new PK8(data);
            rows.Add(new
            {
                sample,
                stage,
                slot = slot.Name,
                address,
                species = pk.Species,
                checksumValid = pk.ChecksumValid,
                encryptionConstant = pk.EncryptionConstant.ToString("X8"),
                isShiny = pk.ChecksumValid ? pk.IsShiny : (bool?)null,
            });
            parsedCount++;
        }
        catch (Exception ex)
        {
            rows.Add(new { sample, stage, slot = slot.Name, address, bytes = data.Length, error = ex.GetType().Name, message = ex.Message });
        }
    }
}

Console.WriteLine(JsonSerializer.Serialize(new { parsedRecords = parsedCount, results = rows }, new JsonSerializerOptions { WriteIndented = true }));
return 0;
