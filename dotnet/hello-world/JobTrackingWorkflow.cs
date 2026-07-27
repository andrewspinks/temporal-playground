// Trimmed/redacted excerpt of our JobTrackingWorkflow for Temporal support review.
// Unrelated members (Pause/Resume/Cancel updates, Continue-As-New/checkpoint restore,
// search-attribute upserts, lifecycle status helpers) have been removed for brevity —
// they are not part of the failing path. Internal constants have been inlined as literal
// strings/comments so this file is self-contained.
//
// Relevant signals (sent externally, in this order, per Event History):
//   1) RegisterFileAsync(fact)              -> adds file to _trackedFiles
//   2) OnFileBoundaryReachedAsync(fact)      -> marks file's CompletedStage
// Relevant update:
//   AdvanceAsync()                          -> fails with "No files to advance" when
//                                               _trackedFiles has zero non-deleted entries

using Temporalio.Workflows;


[Workflow]
public class JobTrackingWorkflow
{
    // Simplified: production ctor takes an IWorkflowWrapper testing seam, omitted here.

    private readonly Dictionary<long, FileTrackingState> _trackedFiles = new();
    private bool _isPaused;
    private bool _isCancelled;
    private bool _isConsumerControlled;
    private string _completedStage = string.Empty;
    private string _nextAction = string.Empty;
    private string? _nextStage;
    private bool _awaitingAction;

    // Boundary rank table used to decide whether a file's CompletedStage satisfies the
    // boundary required for the current NextStage.
    private static readonly Dictionary<string, int> BoundaryRank = new(StringComparer.OrdinalIgnoreCase)
    {
        ["VirusCheckComplete"] = 1,
        ["DocumentClassificationComplete"] = 2,
        ["DocumentExtractionComplete"] = 3,
        ["DocumentProcessComplete"] = 4
    };

    // NextStage -> required boundary before Advance is allowed to proceed.
    private static readonly Dictionary<string, string> RequiredBoundaryByNextStage = new(StringComparer.OrdinalIgnoreCase)
    {
        ["extraction"] = "DocumentClassificationComplete",
        ["postprocessing"] = "DocumentExtractionComplete"
    };

    [WorkflowRun]
    public async Task<WorkflowResult> ProcessAsync(WorkflowStartInput input)
    {
        // Real run started with input.Files = [] (no seed files) and
        // EffectiveExecutionMode = "consumer-controlled", EffectiveScanProfile = "full".
        // _nextStage is initialized to "extraction" and _nextAction to "advance" for this profile/mode.
        _nextStage = "extraction";
        _nextAction = "advance";

        foreach (var file in input.Files)
        {
            _trackedFiles[file.LegacyFileId] = new FileTrackingState
            {
                ExternalFileId = file.FileId.ToString(),
                IsDeleted = false,
                IsTerminal = false,
                CompletedStage = null
            };
        }

        RecomputeControlState();

        await Workflow.WaitConditionAsync(() => _isCancelled || Workflow.ContinueAsNewSuggested);

        return new WorkflowResult { Success = !_isCancelled };
    }

    [WorkflowQuery]
    public JobControlQuery GetJobControl() => new()
    {
        Control = new JobControlState
        {
            AwaitingAction = _awaitingAction && !_isPaused && !_isCancelled,
            CompletedStage = _completedStage,
            NextAction = string.IsNullOrWhiteSpace(_nextAction) ? null : _nextAction,
            NextStage = _nextStage
        }
    };

    [WorkflowSignal]
    public async Task RegisterFileAsync(FileRegistrationFact fact)
    {
        ArgumentNullException.ThrowIfNull(fact);
        if (!_trackedFiles.ContainsKey(fact.FileId))
        {
            _trackedFiles[fact.FileId] = new FileTrackingState
            {
                ExternalFileId = fact.ExternalFileId,
                IsDeleted = false,
                IsTerminal = false,
                CompletedStage = null
            };
        }

        RecomputeControlState();
        await Task.CompletedTask;
    }

    [WorkflowSignal]
    public async Task OnFileBoundaryReachedAsync(BoundaryReachedFact fact)
    {
        ArgumentNullException.ThrowIfNull(fact);
        if (_trackedFiles.TryGetValue(fact.FileId, out var state))
        {
            state.CompletedStage = fact.BoundaryStage;
        }

        RecomputeControlState();
        await Task.CompletedTask;
    }

    [WorkflowUpdate]
    public async Task<AdvanceUpdateResult> AdvanceAsync()
    {
        if (_isPaused)
            return new AdvanceUpdateResult { Success = false, ErrorMessage = "Job is paused" };

        if (_isCancelled)
            return new AdvanceUpdateResult { Success = false, ErrorMessage = "Job is cancelled" };

        // *** This is the check that fails in production: _trackedFiles is observed empty. ***
        var nonDeletedFiles = _trackedFiles.Values.Where(f => !f.IsDeleted).ToList();
        if (nonDeletedFiles.Count == 0)
            return new AdvanceUpdateResult { Success = false, ErrorMessage = "No files to advance" };

        var survivingFiles = nonDeletedFiles.Where(f => !f.IsTerminal).ToList();
        if (survivingFiles.Count == 0)
            return new AdvanceUpdateResult { Success = false, ErrorMessage = "All files terminal" };

        // ... remaining boundary validation + stage transition omitted (not reached in the failure case) ...

        await Task.CompletedTask;
        return new AdvanceUpdateResult { Success = true };
    }

    private void RecomputeControlState()
    {
        if (!_isConsumerControlled || _isPaused || _isCancelled
            || string.IsNullOrWhiteSpace(_nextAction) || string.IsNullOrWhiteSpace(_nextStage))
        {
            _awaitingAction = false;
            return;
        }

        var survivingFiles = _trackedFiles.Values
            .Where(file => !file.IsDeleted && !file.IsTerminal)
            .ToList();

        if (survivingFiles.Count == 0)
        {
            _awaitingAction = false;
            return;
        }

        var requiredBoundary = RequiredBoundaryByNextStage.GetValueOrDefault(_nextStage);
        _awaitingAction = requiredBoundary is null
            || survivingFiles.All(file => IsAtOrBeyondBoundary(file.CompletedStage, requiredBoundary));

        if (_awaitingAction && requiredBoundary is not null)
            _completedStage = requiredBoundary;
    }

    private static bool IsAtOrBeyondBoundary(string? currentBoundary, string requiredBoundary)
    {
        if (string.IsNullOrWhiteSpace(currentBoundary))
            return false;

        if (!BoundaryRank.TryGetValue(requiredBoundary, out var requiredRank))
            return string.Equals(currentBoundary, requiredBoundary, StringComparison.OrdinalIgnoreCase);

        if (!BoundaryRank.TryGetValue(currentBoundary, out var currentRank))
            return false;

        return currentRank >= requiredRank;
    }
}

// ─── Supporting types (simplified) ───

public class FileTrackingState
{
    public string ExternalFileId { get; set; } = string.Empty;
    public bool IsDeleted { get; set; }
    public bool IsTerminal { get; set; }
    public string? CompletedStage { get; set; }
}

public class FileRegistrationFact
{
    public long FileId { get; set; }
    public string ExternalFileId { get; set; } = string.Empty;
}

public class BoundaryReachedFact
{
    public long FileId { get; set; }
    public string BoundaryStage { get; set; } = string.Empty;
}

public class AdvanceUpdateResult
{
    public bool Success { get; set; }
    public string? ErrorMessage { get; set; }
}

public class JobControlQuery
{
    public JobControlState Control { get; set; } = new();
}

public class JobControlState
{
    public bool AwaitingAction { get; set; }
    public string? CompletedStage { get; set; }
    public string? NextAction { get; set; }
    public string? NextStage { get; set; }
}

public class WorkflowResult
{
    public bool Success { get; set; }
}

public class WorkflowStartInput
{
    public List<FileRef> Files { get; set; } = [];
}

public class FileRef
{
    public long LegacyFileId { get; set; }
    public Guid FileId { get; set; }
}
