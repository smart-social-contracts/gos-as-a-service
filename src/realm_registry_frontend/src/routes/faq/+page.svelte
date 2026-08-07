<script>
  import { _ } from 'svelte-i18n';

  const faqs = [
    {
      id: 'credits',
      question: 'What are Credits?',
      answer: `Credits are the internal currency used within the Realms platform. They are used to:
        <ul>
          <li>Pay for ICP (Internet Computer Protocol) resources</li>
          <li>Support the development and maintenance of the Realm Registry</li>
          <li>Maintain realms that have been deployed</li>
          <li>Support the curation of extensions</li>
          <li>Further develop the Realms GOS (Governance Operating System)</li>
        </ul>
        <p><strong>Important:</strong> Credits can only be used within the Realms platform. They are <strong>NOT</strong> tokens and cannot be transferred, traded, or used outside the platform.</p>`
    },
    {
      id: 'pricing',
      question: 'How much do Credits cost?',
      answer: '1 Credit = $1 USD. You can purchase credits in amounts from 1 to 50 at a time through our secure payment system.'
    },
    {
      id: 'vouchers',
      question: 'What are Voucher Codes?',
      answer: 'Voucher codes are promotional codes that can be redeemed for free credits. They may be distributed during special events, partnerships, or promotional campaigns. Each voucher can typically only be redeemed once per user.'
    },
    {
      id: 'realms',
      question: 'What is a Realm?',
      answer: 'A Realm is a self-governed digital community deployed on the Internet Computer. Each realm has its own governance structure, token economy, and can be customized with various extensions to fit its specific needs.'
    },
    {
      id: 'deployment',
      question: 'How do I deploy a Realm?',
      answer: 'You can deploy a realm using our Create Realm wizard. The wizard guides you through setting up your realm\'s basic information, branding, token configuration, governance structure, and extensions. A minimum of 5 credits is required for automatic deployment.'
    },
    {
      id: 'extensions',
      question: 'What are Extensions?',
      answer: 'Extensions are additional features and capabilities that can be added to your realm. They include governance tools, communication features, AI assistants, and more. Extensions are curated and maintained by the Realms community.'
    },
    {
      id: 'refunds',
      question: 'Can I get a refund for Credits?',
      answer: 'Credits are non-refundable once purchased. However, they never expire and can be used at any time for platform services. If you experience any issues with your purchase, please contact support.'
    }
  ];

  let openFaq = 'credits';

  function toggleFaq(id) {
    openFaq = openFaq === id ? null : id;
  }
</script>

<svelte:head>
  <title>FAQ | Realms</title>
</svelte:head>

<div class="faq-page">
  <div class="faq-container">
    <header class="faq-header">
      <a href="/" class="back-link">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        Back to Realms
      </a>
      <h1>Frequently Asked Questions</h1>
      <p class="subtitle">Everything you need to know about the Realms platform</p>
    </header>

    <div class="faq-list">
      {#each faqs as faq}
        <div class="faq-item" class:open={openFaq === faq.id}>
          <button 
            class="faq-question"
            on:click={() => toggleFaq(faq.id)}
            aria-expanded={openFaq === faq.id}
          >
            <span>{faq.question}</span>
            <svg 
              class="chevron" 
              width="20" 
              height="20" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              stroke-width="2"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>
          {#if openFaq === faq.id}
            <div class="faq-answer">
              {@html faq.answer}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <div class="contact-section">
      <h2>Still have questions?</h2>
      <p>Contact us at <a href="mailto:support@realmsgos.org">support@realmsgos.org</a></p>
    </div>
  </div>
</div>

<style>
  .faq-page {
    min-height: 100vh;
    background: #FAFAFA;
    padding: 2rem;
  }

  .faq-container {
    max-width: 800px;
    margin: 0 auto;
  }

  .faq-header {
    margin-bottom: 2rem;
  }

  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: #525252;
    text-decoration: none;
    font-size: 0.875rem;
    margin-bottom: 1rem;
    transition: color 0.15s ease;
  }

  .back-link:hover {
    color: #171717;
  }

  .faq-header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #171717;
    margin: 0 0 0.5rem 0;
  }

  .subtitle {
    color: #525252;
    font-size: 1rem;
    margin: 0;
  }

  .faq-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .faq-item {
    background: #FFFFFF;
    border-radius: 0.75rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }

  .faq-question {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.25rem 1.5rem;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    text-align: left;
    transition: background 0.15s ease;
  }

  .faq-question:hover {
    background: #F5F5F5;
  }

  .chevron {
    transition: transform 0.2s ease;
    flex-shrink: 0;
    color: #737373;
  }

  .faq-item.open .chevron {
    transform: rotate(180deg);
  }

  .faq-answer {
    padding: 0 1.5rem 1.5rem 1.5rem;
    color: #525252;
    line-height: 1.6;
    font-size: 0.9375rem;
  }

  .faq-answer :global(ul) {
    margin: 0.75rem 0;
    padding-left: 1.5rem;
  }

  .faq-answer :global(li) {
    margin-bottom: 0.5rem;
  }

  .faq-answer :global(p) {
    margin: 1rem 0 0 0;
  }

  .faq-answer :global(strong) {
    color: #171717;
  }

  .contact-section {
    margin-top: 3rem;
    text-align: center;
    padding: 2rem;
    background: #FFFFFF;
    border-radius: 0.75rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .contact-section h2 {
    font-size: 1.25rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.5rem 0;
  }

  .contact-section p {
    color: #525252;
    margin: 0;
  }

  .contact-section a {
    color: #171717;
    font-weight: 500;
  }

  .contact-section a:hover {
    text-decoration: none;
  }

  @media (max-width: 768px) {
    .faq-page {
      padding: 1rem;
    }

    .faq-header h1 {
      font-size: 1.5rem;
    }

    .faq-question {
      padding: 1rem;
      font-size: 0.9375rem;
    }

    .faq-answer {
      padding: 0 1rem 1rem 1rem;
    }
  }
</style>
