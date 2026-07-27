package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp02: telephone must be 6 to 15 digits. */
@Tag("cp02")
class Cp02Tests extends AcceptanceBase {

	@Test
	void coreRejectsTooShortTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "12345"); // 5 digits
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void coreAcceptsTenDigitTelephone() throws Exception {
		createOwner(validOwner()).andExpect(status().is2xxSuccessful()); // uniquePhone() is 10 digits
	}

	@Test
	void errorRejectsNonDigitTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "12ab567"); // letters are never valid, even after formatting is stripped
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityRejectsTooLongTelephone() throws Exception {
		ObjectNode o = validOwner();
		o.put("telephone", "1234567890123456"); // 16 digits
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsBoundaryLengths() throws Exception {
		ObjectNode six = validOwner();
		six.put("telephone", "123456");
		createOwner(six).andExpect(status().is2xxSuccessful());
		ObjectNode fifteen = validOwner();
		fifteen.put("telephone", "123456789012345");
		createOwner(fifteen).andExpect(status().is2xxSuccessful());
	}
}
