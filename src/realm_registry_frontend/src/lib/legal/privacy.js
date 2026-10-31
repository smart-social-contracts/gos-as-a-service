import {
  LEGAL_ADDRESS_PLACEHOLDER,
  LEGAL_CONTACT_EMAIL,
  LEGAL_NAME_PLACEHOLDER,
} from './legal-info.js';

/** Privacy Policy for the Alpha, by locale. Each section: heading and paragraphs (plain text). */
export const PRIVACY = {
  en: {
    title: 'Privacy Policy',
    alphaNotice: 'Alpha version. This policy is a plain-language draft and has not yet been reviewed by a lawyer.',
    sections: [
      {
        heading: '1. Who is responsible',
        paragraphs: [
          `Smart Social Contracts (${LEGAL_NAME_PLACEHOLDER}, ${LEGAL_ADDRESS_PLACEHOLDER}) is the controller for gos.earth and realmsgos.org. Contact for anything about your data: ${LEGAL_CONTACT_EMAIL}. This policy follows the Swiss Federal Act on Data Protection (revFADP) and the EU General Data Protection Regulation (GDPR).`,
        ],
      },
      {
        heading: '2. What we collect and why',
        paragraphs: [
          'Invitation request: your email address and your answers on the invitation form. The form is run by Tally (tally.so), which processes it for us. We use it to review your request and email you an invitation code.',
          'Account: your Internet Identity principal (a pseudonymous identifier, not your name), your credits, the hash of the invitation code you used, your unfinished realm setups and the realms you deploy. We use it to run the Service.',
          'AI assistant: the questions you ask, your principal and the realm you are in are sent to our assistant service (ggg-ai), which has an AI model of Infomaniak AI Tools answer them. Conversations are stored in its database so you can come back to them; you can delete a conversation in the app.',
          'MCP server and AI assistants: if you connect an AI assistant (Claude, ChatGPT, …) to our MCP server, we store your approval of that connection (only hashes of its tokens) and an identity for it, which is what you grant power of attorney to. Anything the assistant does with that power is recorded in the realm as your action.',
          'Your browser keeps preferences and drafts locally. We use no advertising or analytics trackers.',
        ],
      },
      {
        heading: '3. Data on the Internet Computer',
        paragraphs: [
          'The registry and every realm run on the Internet Computer, a public network of independent node machines in many countries. Data on it is replicated across nodes. Depending on the realm, it may be readable by anyone, including your principal, your membership, your votes and what you write.',
          'Such data can be very hard or impossible to delete or correct, even for us. This limits some of your rights below for on-chain data. Do not put personal data on-chain that you are not willing to have public for good.',
        ],
      },
      {
        heading: '4. Who else receives data',
        paragraphs: [
          'Tally (invitation form). Infomaniak (Switzerland): sends our email, including your invitation code, and runs the AI model. The Internet Computer nodes that host the registry and the realms. We do not sell personal data.',
          'Some of these recipients are outside Switzerland and the EU/EEA. Where that is so, we rely on adequacy decisions or standard contractual clauses.',
        ],
      },
      {
        heading: '5. Legal basis and retention',
        paragraphs: [
          'We process data to give you the access and features you asked for (contract), for our legitimate interest in running and securing the Alpha, and with your consent where you give it, for example on the invitation form. You can withdraw consent at any time.',
          'We keep invitation requests and assistant conversations only as long as the Alpha needs them, and we delete them when you ask. We may delete everything when the Alpha ends. On-chain data stays as described above.',
        ],
      },
      {
        heading: '6. Your rights',
        paragraphs: [
          `You may ask for access to your data, correction, deletion, restriction, a copy in a usable format, and object to our processing. Write to ${LEGAL_CONTACT_EMAIL} from the address you used on the form, and tell us your principal if the request concerns your account. We answer within 30 days. We may ask you to prove who you are.`,
          'You may also complain to the Swiss Federal Data Protection and Information Commissioner (FDPIC) or to the data protection authority in your EU country.',
        ],
      },
    ],
  },
  es: {
    title: 'Política de privacidad',
    alphaNotice: 'Versión Alpha. Esta política es un borrador en lenguaje sencillo y aún no la ha revisado un abogado.',
    sections: [
      {
        heading: '1. Responsable',
        paragraphs: [
          `Smart Social Contracts (${LEGAL_NAME_PLACEHOLDER}, ${LEGAL_ADDRESS_PLACEHOLDER}) es el responsable del tratamiento de gos.earth y realmsgos.org. Contacto para cualquier asunto sobre sus datos: ${LEGAL_CONTACT_EMAIL}. Esta política sigue la Ley Federal suiza de Protección de Datos (revLPD) y el Reglamento General de Protección de Datos de la UE (RGPD).`,
        ],
      },
      {
        heading: '2. Qué recogemos y para qué',
        paragraphs: [
          'Solicitud de invitación: su correo electrónico y sus respuestas en el formulario de invitación. El formulario lo gestiona Tally (tally.so), que lo trata por encargo nuestro. Lo usamos para revisar su solicitud y enviarle un código de invitación.',
          'Cuenta: su principal de Internet Identity (un identificador seudónimo, no su nombre), sus créditos, el hash del código de invitación que usó, sus configuraciones de realm sin terminar y los realms que despliega. Lo usamos para prestar el Servicio.',
          'Asistente de IA: sus preguntas, su principal y el realm en el que está se envían a nuestro servicio de asistente (ggg-ai), que hace que un modelo de IA de Infomaniak AI Tools las responda. Las conversaciones se guardan en su base de datos para que pueda retomarlas; puede borrar una conversación en la aplicación.',
          'Servidor MCP y asistentes de IA: si conecta un asistente de IA (Claude, ChatGPT, …) a nuestro servidor MCP, guardamos su aprobación de esa conexión (solo hashes de sus tokens) y una identidad para ella, que es a quien usted otorga el poder notarial. Todo lo que el asistente haga con ese poder queda registrado en el realm como acción suya.',
          'Su navegador guarda localmente preferencias y borradores. No usamos rastreadores publicitarios ni de analítica.',
        ],
      },
      {
        heading: '3. Datos en Internet Computer',
        paragraphs: [
          'El registro y cada realm funcionan en Internet Computer, una red pública de máquinas independientes en muchos países. Los datos se replican entre nodos. Según el realm, pueden ser legibles por cualquiera: su principal, su pertenencia, sus votos y lo que escriba.',
          'Esos datos pueden ser muy difíciles o imposibles de borrar o corregir, incluso para nosotros. Esto limita algunos de sus derechos, abajo, respecto de los datos en la cadena. No ponga en la cadena datos personales que no acepte hacer públicos para siempre.',
        ],
      },
      {
        heading: '4. Quién más recibe datos',
        paragraphs: [
          'Tally (formulario de invitación). Infomaniak (Suiza): envía nuestro correo, incluido su código de invitación, y ejecuta el modelo de IA. Los nodos de Internet Computer que alojan el registro y los realms. No vendemos datos personales.',
          'Algunos de estos destinatarios están fuera de Suiza y del EEE/UE. En ese caso nos basamos en decisiones de adecuación o en cláusulas contractuales tipo.',
        ],
      },
      {
        heading: '5. Base jurídica y conservación',
        paragraphs: [
          'Tratamos los datos para darle el acceso y las funciones que pidió (contrato), por nuestro interés legítimo en operar y proteger el Alpha y, cuando usted lo da, con su consentimiento, por ejemplo en el formulario de invitación. Puede retirar el consentimiento en cualquier momento.',
          'Conservamos las solicitudes de invitación y las conversaciones del asistente solo mientras el Alpha las necesite y las borramos si nos lo pide. Podemos borrarlo todo al terminar el Alpha. Los datos en la cadena permanecen como se ha descrito.',
        ],
      },
      {
        heading: '6. Sus derechos',
        paragraphs: [
          `Puede pedir acceso a sus datos, su rectificación, supresión o limitación, una copia en formato utilizable, y oponerse a nuestro tratamiento. Escriba a ${LEGAL_CONTACT_EMAIL} desde la dirección que usó en el formulario e indíquenos su principal si la solicitud afecta a su cuenta. Respondemos en 30 días. Podemos pedirle que acredite su identidad.`,
          'También puede reclamar ante el Encargado Federal suizo de Protección de Datos y Transparencia (PFPDT) o ante la autoridad de protección de datos de su país de la UE.',
        ],
      },
    ],
  },
};
