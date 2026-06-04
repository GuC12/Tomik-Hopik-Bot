using UnityEngine;

[RequireComponent(typeof(Rigidbody2D))]
public class PlayerController2D : MonoBehaviour
{
    [Header("Movement")]
    [SerializeField] private float moveSpeed = 7f;
    [SerializeField] private float acceleration = 60f;
    [SerializeField] private float deceleration = 70f;

    [Header("Jump")]
    [SerializeField] private float jumpForce = 14f;
    [SerializeField] private float fallMultiplier = 2.4f;
    [SerializeField] private float lowJumpMultiplier = 2f;
    [SerializeField] private float coyoteTime = 0.12f;
    [SerializeField] private float jumpBufferTime = 0.12f;

    [Header("Ground Check")]
    [SerializeField] private Transform groundCheck;
    [SerializeField] private Vector2 groundCheckSize = new Vector2(0.55f, 0.12f);
    [SerializeField] private LayerMask groundLayer;

    [Header("Animation")]
    [SerializeField] private Animator animator;
    [SerializeField] private SpriteRenderer spriteRenderer;

    private Rigidbody2D rb;
    private float horizontalInput;
    private float coyoteCounter;
    private float jumpBufferCounter;
    private bool isGrounded;
    private bool isJumpHeld;

    private static readonly int SpeedHash = Animator.StringToHash("Speed");
    private static readonly int IsGroundedHash = Animator.StringToHash("IsGrounded");
    private static readonly int VerticalSpeedHash = Animator.StringToHash("VerticalSpeed");
    private static readonly int JumpHash = Animator.StringToHash("Jump");

    private void Awake()
    {
        rb = GetComponent<Rigidbody2D>();

        if (animator == null)
        {
            animator = GetComponentInChildren<Animator>();
        }

        if (spriteRenderer == null)
        {
            spriteRenderer = GetComponentInChildren<SpriteRenderer>();
        }
    }

    private void Update()
    {
        horizontalInput = Input.GetAxisRaw("Horizontal");
        isJumpHeld = Input.GetButton("Jump");

        if (Input.GetButtonDown("Jump"))
        {
            jumpBufferCounter = jumpBufferTime;
        }
        else
        {
            jumpBufferCounter -= Time.deltaTime;
        }

        UpdateGroundedState();
        UpdateTimers();
        TryJump();
        FlipSprite();
        UpdateAnimations();
    }

    private void FixedUpdate()
    {
        Move();
        ImproveJumpFeel();
    }

    private void Move()
    {
        float targetSpeed = horizontalInput * moveSpeed;
        float speedDifference = targetSpeed - rb.linearVelocity.x;
        float rate = Mathf.Abs(targetSpeed) > 0.01f ? acceleration : deceleration;
        float movement = speedDifference * rate;

        rb.AddForce(Vector2.right * movement);

        if (Mathf.Abs(rb.linearVelocity.x) > moveSpeed)
        {
            rb.linearVelocity = new Vector2(Mathf.Sign(rb.linearVelocity.x) * moveSpeed, rb.linearVelocity.y);
        }
    }

    private void UpdateGroundedState()
    {
        if (groundCheck == null)
        {
            isGrounded = false;
            return;
        }

        isGrounded = Physics2D.OverlapBox(groundCheck.position, groundCheckSize, 0f, groundLayer);
    }

    private void UpdateTimers()
    {
        if (isGrounded)
        {
            coyoteCounter = coyoteTime;
        }
        else
        {
            coyoteCounter -= Time.deltaTime;
        }
    }

    private void TryJump()
    {
        if (jumpBufferCounter > 0f && coyoteCounter > 0f)
        {
            rb.linearVelocity = new Vector2(rb.linearVelocity.x, jumpForce);
            jumpBufferCounter = 0f;
            coyoteCounter = 0f;

            if (animator != null)
            {
                animator.SetTrigger(JumpHash);
            }
        }
    }

    private void ImproveJumpFeel()
    {
        if (rb.linearVelocity.y < 0f)
        {
            rb.linearVelocity += Vector2.up * (Physics2D.gravity.y * (fallMultiplier - 1f) * Time.fixedDeltaTime);
        }
        else if (rb.linearVelocity.y > 0f && !isJumpHeld)
        {
            rb.linearVelocity += Vector2.up * (Physics2D.gravity.y * (lowJumpMultiplier - 1f) * Time.fixedDeltaTime);
        }
    }

    private void FlipSprite()
    {
        if (spriteRenderer == null || Mathf.Abs(horizontalInput) < 0.01f)
        {
            return;
        }

        spriteRenderer.flipX = horizontalInput < 0f;
    }

    private void UpdateAnimations()
    {
        if (animator == null)
        {
            return;
        }

        animator.SetFloat(SpeedHash, Mathf.Abs(rb.linearVelocity.x));
        animator.SetBool(IsGroundedHash, isGrounded);
        animator.SetFloat(VerticalSpeedHash, rb.linearVelocity.y);
    }

    private void OnDrawGizmosSelected()
    {
        if (groundCheck == null)
        {
            return;
        }

        Gizmos.color = Color.green;
        Gizmos.DrawWireCube(groundCheck.position, groundCheckSize);
    }
}
