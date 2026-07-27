package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp16: reject names containing digits or control characters. */
@Tag("cp16")
class Cp16Tests extends AcceptanceBase {

	// A BEL control character, built explicitly so nothing hides in the source.
	private static final String CONTROL_CHAR = "Smi" + ((char) 7) + "th";

	@Test
	void coreRejectsDigitsInName() throws Exception {
		ObjectNode o = validOwner();
		o.put("firstName", "John3");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsControlCharInName() throws Exception {
		ObjectNode o = validOwner();
		o.put("lastName", CONTROL_CHAR);
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsHyphenAndApostrophe() throws Exception {
		createOwner(validOwner("Anne-Marie", "O'Neill")).andExpect(status().is2xxSuccessful());
	}
}
